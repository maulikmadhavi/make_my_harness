"""Tests for loop.run_turn — offline, with a scripted stub LLM.

Focus: the short-circuit for repeated identical tool calls. The nudge is
delivered as the tool result itself so every tool_call id still gets a
role:"tool" response (the pairing rule the deny path also honors).
"""

import pytest
from helpers import StubLog

from make_harness.loop import DENIED_RESULT, SHORT_CIRCUIT_RESULT, _repair_args, run_turn
from make_harness.tools import Registry


class ScriptedLLM:
    """Returns pre-scripted responses in order, ignoring the input."""

    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, tools=None):
        r = self.responses.pop(0)
        return {
            "content": r.get("content"),
            "reasoning": r.get("reasoning"),
            "tool_calls": r.get("tool_calls", []),
            "usage": {},
            "raw": r,
        }


class AllowAll:
    def __init__(self):
        self.checked = []

    def check(self, name, args):
        self.checked.append(name)
        return "allow"


class DenyAll:
    def check(self, name, args):
        return "deny"


def _tc(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def _make_registry():
    reg = Registry()
    calls = []

    @reg.tool
    def probe(path: str) -> str:
        """Read something."""
        calls.append(path)
        return f"content of {path}"

    return reg, calls


def _pairing_ok(messages):
    """Every tool_calls id must be answered by a following tool message."""
    expected = []
    for m in messages:
        if m.get("tool_calls"):
            expected += [tc["id"] for tc in m["tool_calls"]]
    answered = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
    return expected == answered


def test_plain_answer_no_tools():
    llm = ScriptedLLM([{"content": "hello"}])
    reg, _ = _make_registry()
    messages = [{"role": "user", "content": "hi"}]
    answer = run_turn(llm, reg, AllowAll(), StubLog(), messages)
    assert answer == "hello"
    assert messages[-1] == {"role": "assistant", "content": "hello"}


def test_identical_repeat_is_short_circuited():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"tool_calls": [_tc("c2", "probe", '{"path": "x.py"}')]},  # verbatim repeat
        {"content": "done"},
    ])
    reg, calls = _make_registry()
    log = StubLog()
    messages = [{"role": "user", "content": "go"}]
    answer = run_turn(llm, reg, AllowAll(), log, messages)
    assert answer == "done"
    assert calls == ["x.py"]  # executed exactly once
    tool_results = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    assert tool_results["c1"] == "content of x.py"
    assert tool_results["c2"] == SHORT_CIRCUIT_RESULT
    assert _pairing_ok(messages)
    assert ("short_circuit", {"step": 1, "tool": "probe", "id": "c2"}) in log.events


def test_different_args_are_not_short_circuited():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"tool_calls": [_tc("c2", "probe", '{"path": "y.py"}')]},
        {"content": "done"},
    ])
    reg, calls = _make_registry()
    run_turn(llm, reg, AllowAll(), StubLog(), [{"role": "user", "content": "go"}])
    assert calls == ["x.py", "y.py"]


def test_duplicate_within_one_batch_runs_once():
    llm = ScriptedLLM([
        {"tool_calls": [
            _tc("c1", "probe", '{"path": "x.py"}'),
            _tc("c2", "probe", '{"path": "x.py"}'),
        ]},
        {"content": "done"},
    ])
    reg, calls = _make_registry()
    messages = [{"role": "user", "content": "go"}]
    run_turn(llm, reg, AllowAll(), StubLog(), messages)
    assert calls == ["x.py"]
    assert _pairing_ok(messages)


def test_argument_key_order_does_not_defeat_the_check():
    reg = Registry()
    calls = []

    @reg.tool
    def pair(a: str, b: str) -> str:
        """Two-arg tool."""
        calls.append((a, b))
        return "ok"

    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "pair", '{"a": "1", "b": "2"}')]},
        {"tool_calls": [_tc("c2", "pair", '{"b": "2", "a": "1"}')]},  # same call, keys reordered
        {"content": "done"},
    ])
    run_turn(llm, reg, AllowAll(), StubLog(), [{"role": "user", "content": "go"}])
    assert calls == [("1", "2")]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('Sure! Here are the arguments: {"path": "x.py"}', {"path": "x.py"}),
        ('<args>{"path": "x.py"}</args>', {"path": "x.py"}),
        ("no braces here", None),
        ("{still: not json}", None),
        ("}{", None),
    ],
    ids=["prose-wrapped", "tag-wrapped", "no-braces", "not-json", "reversed-braces"],
)
def test_repair_args(raw, expected):
    assert _repair_args(raw) == expected


def test_prose_wrapped_arguments_are_repaired_and_executed():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", 'Sure! {"path": "x.py"}')]},
        {"content": "done"},
    ])
    reg, calls = _make_registry()
    log = StubLog()
    messages = [{"role": "user", "content": "go"}]
    answer = run_turn(llm, reg, AllowAll(), log, messages)
    assert answer == "done"
    assert calls == ["x.py"]
    assert "args_repaired" in log.kinds()


def test_unrepairable_arguments_fail_clean():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", "total garbage")]},
        {"content": "done"},
    ])
    reg, calls = _make_registry()
    messages = [{"role": "user", "content": "go"}]
    answer = run_turn(llm, reg, AllowAll(), StubLog(), messages)
    assert answer == "done"
    assert calls == []
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["content"].startswith("Error: unparseable tool arguments")
    assert _pairing_ok(messages)


def test_short_circuit_skips_the_permission_prompt():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"tool_calls": [_tc("c2", "probe", '{"path": "x.py"}')]},
        {"content": "done"},
    ])
    reg, _ = _make_registry()
    policy = AllowAll()
    run_turn(llm, reg, policy, StubLog(), [{"role": "user", "content": "go"}])
    assert policy.checked == ["probe"]  # not re-prompted for the repeat


def test_trace_lines_are_printed_for_each_tool_call(capsys):
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"content": "done"},
    ])
    reg, _ = _make_registry()
    run_turn(llm, reg, AllowAll(), StubLog(), [{"role": "user", "content": "go"}])
    out = capsys.readouterr().out
    assert "probe" in out
    assert "chars" in out


# --- denial, step exhaustion, and the log trail ----------------------------

class ScriptedPolicy:
    """Returns scripted verdicts in order and records every check."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.checked = []

    def check(self, name, args):
        self.checked.append(name)
        return self.verdicts.pop(0)


def test_denial_ends_the_turn_and_hands_control_back():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"content": "should never be reached"},
    ])
    reg, calls = _make_registry()
    log = StubLog()
    messages = [{"role": "user", "content": "go"}]
    answer = run_turn(llm, reg, DenyAll(), log, messages)
    assert answer == "[tool call denied — tell me how to proceed]"
    assert calls == []
    assert messages[-1] == {"role": "tool", "tool_call_id": "c1", "content": DENIED_RESULT}
    assert ("turn_interrupted", {"step": 0}) in log.events
    assert len(llm.responses) == 1  # the second scripted response was never consumed
    assert _pairing_ok(messages)


def test_rest_of_the_batch_is_auto_denied_after_one_denial():
    llm = ScriptedLLM([{"tool_calls": [
        _tc("c1", "probe", '{"path": "a.py"}'),
        _tc("c2", "probe", '{"path": "b.py"}'),
    ]}])
    reg, calls = _make_registry()
    policy = ScriptedPolicy(["deny"])  # only one verdict scripted
    messages = [{"role": "user", "content": "go"}]
    run_turn(llm, reg, policy, StubLog(), messages)
    assert policy.checked == ["probe"]  # the second call was never asked about
    assert calls == []
    assert [m["content"] for m in messages if m["role"] == "tool"] == [DENIED_RESULT, DENIED_RESULT]
    assert _pairing_ok(messages)


def test_max_steps_exhaustion_returns_a_stop_marker():
    llm = ScriptedLLM([
        {"tool_calls": [_tc(f"c{i}", "probe", f'{{"path": "{i}.py"}}')]} for i in range(5)
    ])
    reg, calls = _make_registry()
    log = StubLog()
    answer = run_turn(llm, reg, AllowAll(), log, [{"role": "user", "content": "go"}], max_steps=3)
    assert answer == "[stopped: reached 3 steps without a final answer]"
    assert calls == ["0.py", "1.py", "2.py"]
    assert ("max_steps", {"steps": 3}) in log.events


def test_unknown_tool_name_is_reported_back_to_the_model():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "ghost", "{}")]},
        {"content": "ok, no such tool"},
    ])
    reg, _ = _make_registry()
    messages = [{"role": "user", "content": "go"}]
    answer = run_turn(llm, reg, AllowAll(), StubLog(), messages)
    assert answer == "ok, no such tool"
    assert messages[2] == {"role": "tool", "tool_call_id": "c1", "content": "Error: unknown tool 'ghost'"}


def test_empty_arguments_string_means_no_arguments():
    reg = Registry()
    calls = []

    @reg.tool
    def ping() -> str:
        """No-arg tool."""
        calls.append(1)
        return "pong"

    llm = ScriptedLLM([{"tool_calls": [_tc("c1", "ping", "")]}, {"content": "done"}])
    run_turn(llm, reg, AllowAll(), StubLog(), [{"role": "user", "content": "go"}])
    assert calls == [1]


def test_log_trail_for_one_tool_round_trip():
    llm = ScriptedLLM([
        {"tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"content": "done"},
    ])
    reg, _ = _make_registry()
    log = StubLog()
    run_turn(llm, reg, AllowAll(), log, [{"role": "user", "content": "go"}])
    assert log.kinds() == [
        "llm_request", "llm_response", "tool_call", "permission", "tool_result",
        "llm_request", "llm_response", "done",
    ]
    permission = next(f for k, f in log.events if k == "permission")
    assert permission == {"step": 0, "tool": "probe", "verdict": "allow"}


def test_logged_tool_result_is_capped_but_the_message_is_not():
    reg = Registry()

    @reg.tool
    def big() -> str:
        """Returns a lot."""
        return "x" * 5000

    llm = ScriptedLLM([{"tool_calls": [_tc("c1", "big", "{}")]}, {"content": "done"}])
    log = StubLog()
    messages = [{"role": "user", "content": "go"}]
    run_turn(llm, reg, AllowAll(), log, messages)
    logged = next(f for k, f in log.events if k == "tool_result")
    assert len(logged["result"]) == 2000
    assert len(messages[2]["content"]) == 5000


def test_assistant_tool_call_message_keeps_both_content_and_calls():
    llm = ScriptedLLM([
        {"content": "let me look", "tool_calls": [_tc("c1", "probe", '{"path": "x.py"}')]},
        {"content": "done"},
    ])
    reg, _ = _make_registry()
    messages = [{"role": "user", "content": "go"}]
    run_turn(llm, reg, AllowAll(), StubLog(), messages)
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "let me look"
    assert messages[1]["tool_calls"][0]["id"] == "c1"
