"""Tests for loop.run_turn — offline, with a scripted stub LLM.

Focus: the short-circuit for repeated identical tool calls. The nudge is
delivered as the tool result itself so every tool_call id still gets a
role:"tool" response (the pairing rule the deny path also honors).
"""

from make_harness.loop import SHORT_CIRCUIT_RESULT, _repair_args, run_turn
from make_harness.tools import Registry


class ScriptedLLM:
    """Returns pre-scripted responses in order, ignoring the input."""

    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, tools=None):
        r = self.responses.pop(0)
        return {
            "content": r.get("content"),
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


class StubLog:
    def __init__(self):
        self.events = []

    def event(self, kind, **fields):
        self.events.append((kind, fields))


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


def test_repair_extracts_object_from_prose():
    assert _repair_args('Sure! Here are the arguments: {"path": "x.py"}') == {"path": "x.py"}


def test_repair_extracts_object_from_tags():
    assert _repair_args('<args>{"path": "x.py"}</args>') == {"path": "x.py"}


def test_repair_gives_up_on_garbage():
    assert _repair_args("no braces here") is None
    assert _repair_args("{still: not json}") is None
    assert _repair_args("}{") is None


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
    assert any(kind == "args_repaired" for kind, _ in log.events)


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
