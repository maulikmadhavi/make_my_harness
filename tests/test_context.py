"""Tests for context.compact — the three escalating compaction steps.

Recreates the Stage 5 scratch tests properly (they were written, passed
live, and never committed): stub path, summarize path, tool-pair cut
safety, and the step-3 last resort that fixed the live no-op bug.
"""

from make_harness.context import compact, estimate_tokens


class StubLLM:
    """Stands in for LLMClient during the summarize step — no network."""

    def complete(self, messages, tools=None):
        return {
            "content": "SUMMARY OF OLDER CONVERSATION",
            "tool_calls": [],
            "usage": {},
            "raw": {},
        }


class StubLog:
    def __init__(self):
        self.events = []

    def event(self, kind, **fields):
        self.events.append((kind, fields))


def _msg(role, content, **extra):
    return {"role": role, "content": content, **extra}


def _tool_block(call_id, content):
    """An assistant tool_calls message followed by its tool result."""
    return [
        _msg(
            "assistant",
            None,
            tool_calls=[{
                "id": call_id,
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }],
        ),
        _msg("tool", content, tool_call_id=call_id),
    ]


def _pairing_ok(msgs):
    """Every role:'tool' message must sit directly behind an assistant
    message that carries tool_calls (possibly with sibling tool results
    in between)."""
    for i, m in enumerate(msgs):
        if m["role"] == "tool":
            j = i
            while j > 0 and msgs[j - 1]["role"] == "tool":
                j -= 1
            if j == 0 or not msgs[j - 1].get("tool_calls"):
                return False
    return True


def test_under_budget_is_untouched():
    msgs = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "hello")]
    log = StubLog()
    out = compact(msgs, StubLLM(), log, budget=10_000)
    assert out == msgs
    assert log.events == []


def test_step1_stubs_old_tool_results():
    msgs = [_msg("system", "sys")]
    msgs += _tool_block("c1", "x" * 5000)
    msgs += [_msg("user", f"msg {i}") for i in range(8)]  # protected recent window
    budget = estimate_tokens(msgs) - 1
    log = StubLog()
    out = compact(msgs, StubLLM(), log, budget=budget)
    assert out[2]["content"].endswith("…[stubbed by compaction]")
    assert len(out[2]["content"]) < 300
    assert [kind for kind, _ in log.events] == ["compaction"]
    assert log.events[0][1]["mode"] == "stub-old-tools"
    assert estimate_tokens(out) <= budget
    assert _pairing_ok(out)


def test_step2_summarizes_older_half():
    msgs = [_msg("system", "sys")]
    # Long plain-text history: step 1 (tool stubbing) can't help here.
    msgs += [
        _msg("user" if i % 2 == 0 else "assistant", f"long text {i} " + "y" * 3000)
        for i in range(6)
    ]
    recent = [_msg("user", f"recent {i}") for i in range(8)]
    msgs += recent
    log = StubLog()
    out = compact(msgs, StubLLM(), log, budget=estimate_tokens(msgs) // 2)
    assert len(out) == 2 + len(recent)
    assert out[0]["role"] == "system"  # never touched
    assert out[1]["role"] == "user"
    assert out[1]["content"].startswith("[Conversation so far")
    assert "SUMMARY OF OLDER CONVERSATION" in out[1]["content"]
    assert out[2:] == recent  # recent window preserved verbatim
    assert log.events[0][1]["mode"] == "summarize"


def test_summarize_never_splits_a_tool_pair():
    assistant_tc = _msg(
        "assistant",
        None,
        tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            {"id": "c2", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ],
    )
    msgs = [
        _msg("system", "sys"),
        _msg("user", "u" * 4000),
        _msg("assistant", "a" * 4000),
        assistant_tc,
        _msg("tool", "result one", tool_call_id="c1"),
        _msg("tool", "result two", tool_call_id="c2"),
    ]
    msgs += [_msg("user", f"recent {i}") for i in range(7)]
    # The naive cut point (len - KEEP_RECENT) lands between the two tool
    # results — exactly the case _safe_cut must move past.
    assert msgs[len(msgs) - 8]["role"] == "tool"
    log = StubLog()
    out = compact(msgs, StubLLM(), log, budget=estimate_tokens(msgs) // 2)
    assert _pairing_ok(out)
    assert log.events[0][1]["mode"] == "summarize"


def test_step3_stubs_recent_tools_when_nothing_older_exists():
    # The Stage 5 live bug: a conversation shorter than the protected
    # window could never be compacted — one huge read blew the budget
    # while compaction logged "success" doing nothing.
    msgs = [_msg("system", "sys")]
    msgs += _tool_block("c1", "z" * 8000)
    msgs.append(_msg("user", "so what does it say?"))
    log = StubLog()
    out = compact(msgs, StubLLM(), log, budget=300)
    assert log.events[0][1]["mode"] == "stub-recent-tools"
    assert out[2]["content"].endswith("…[stubbed by compaction]")
    assert estimate_tokens(out) <= 300
    assert _pairing_ok(out)
