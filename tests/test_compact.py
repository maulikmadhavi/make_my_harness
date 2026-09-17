"""Tests for compact — when compaction is needed, where the kept tail
starts, and the system + handoff note + tail it leaves behind."""

import pytest
from helpers import StubLLM, StubLog

from make_harness import compact, config
from make_harness.history import SUMMARY, TRIMMED, estimate, locked


@pytest.fixture
def window(monkeypatch):
    """A 1000-token window: compact above 850, keep a ~350-token tail."""
    monkeypatch.setattr(config, "CONTEXT_WINDOW", 1000)


def _conversation(turns=12, size=400):
    """system, then `turns` user/assistant exchanges of ~size chars each,
    with a tool round-trip in the middle of every exchange."""
    messages = [{"role": "system", "content": "system prompt"}]
    for i in range(turns):
        messages += [
            {"role": "user", "content": f"question {i} " + "q" * size},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "r" * size},
            {"role": "assistant", "content": f"answer {i}"},
        ]
    return messages


class RecordingLLM(StubLLM):
    def __init__(self):
        self.requests = []

    def complete(self, messages, tools=None):
        self.requests.append(messages)
        return super().complete(messages, tools)


class TestNeeded:
    def test_uses_the_servers_prompt_tokens(self, window):
        assert compact.needed({"prompt_tokens": 851}, []) is True
        assert compact.needed({"prompt_tokens": 849}, _conversation()) is False  # estimate ignored

    def test_falls_back_to_the_estimate_without_usage(self, window):
        big = _conversation()
        assert estimate(big) > 850
        assert compact.needed({}, big) is True
        assert compact.needed(None, big[:2]) is False


class TestTailStart:
    def test_everything_fits_returns_one(self):
        assert compact.tail_start(_conversation(turns=2), budget=10**6) == 1

    def test_never_starts_on_a_tool_result(self):
        messages = _conversation()
        for budget in range(50, 2000, 37):
            cut = compact.tail_start(messages, budget)
            assert cut == len(messages) or messages[cut]["role"] != "tool"

    def test_tail_stays_within_budget(self):
        messages = _conversation()
        cut = compact.tail_start(messages, budget=600)
        assert estimate(messages[cut:]) <= 600


class TestCompact:
    def test_short_conversation_returns_none_without_an_llm_call(self, window):
        messages = _conversation(turns=1, size=10)
        llm = RecordingLLM()
        assert compact.compact(messages, llm, StubLog()) is None
        assert llm.requests == []

    def test_leaves_system_handoff_and_recent_tail(self, window):
        messages = _conversation()
        original = [dict(m) for m in messages]
        log = StubLog()
        out = compact.compact(messages, StubLLM(), log)
        assert out[0] == messages[0]
        assert out[1]["role"] == "user"
        assert out[1]["content"].startswith(SUMMARY)
        assert "SUMMARY OF OLDER CONVERSATION" in out[1]["content"]
        assert out[1]["content"].endswith("</summary>")
        assert locked(out) == 2
        assert estimate(out) < estimate(messages)
        assert [m["role"] for m in out[2:]] == [m["role"] for m in messages[-len(out[2:]):]]
        assert messages == original  # the input list and its dicts are untouched
        kind, fields = log.events[0]
        assert kind == "compaction"
        assert fields["summarized"] == len(messages) - len(out[2:]) - 1
        assert fields["kept_original"] is False
        assert fields["summary"] == "SUMMARY OF OLDER CONVERSATION"

    def test_no_tool_result_is_orphaned(self, window):
        out = compact.compact(_conversation(), StubLLM(), StubLog())
        called = {c["id"] for m in out if m.get("tool_calls") for c in m["tool_calls"]}
        answered = {m["tool_call_id"] for m in out if m["role"] == "tool"}
        assert answered <= called

    def test_kept_tail_tool_results_are_stripped(self, window):
        out = compact.compact(_conversation(size=600), StubLLM(), StubLog())
        assert all(TRIMMED in m["content"] for m in out if m["role"] == "tool")

    def test_summarizer_sees_the_older_transcript_as_text(self, window):
        llm = RecordingLLM()
        compact.compact(_conversation(), llm, StubLog())
        system, user = llm.requests[0]
        assert system == {"role": "system", "content": compact.SUMMARY_PROMPT}
        assert user["content"].startswith("<transcript>\nUSER: question 0")
        assert user["content"].endswith("</transcript>\n\n" + compact.SUMMARY_REQUEST)
        assert "[called read_file({})]" in user["content"]
        assert "TOOL RESULT: rrr" in user["content"]
        assert "system prompt" not in user["content"]

    def test_a_summary_no_smaller_than_the_original_is_discarded(self, window):
        class VerboseLLM(StubLLM):
            def complete(self, messages, tools=None):
                return {**super().complete(messages, tools), "content": "y" * 50_000}

        messages = _conversation()
        log = StubLog()
        assert compact.compact(messages, VerboseLLM(), log) is messages
        assert log.events[0][1]["kept_original"] is True

    def test_a_failing_summary_call_raises_and_leaves_messages_intact(self, window):
        class FailingLLM:
            def complete(self, messages, tools=None):
                raise RuntimeError("rate limited")

        messages = _conversation()
        original = [dict(m) for m in messages]
        with pytest.raises(RuntimeError):
            compact.compact(messages, FailingLLM(), StubLog())
        assert messages == original

    def test_a_second_compaction_folds_in_the_first_summary(self, window):
        llm = RecordingLLM()
        once = compact.compact(_conversation(), llm, StubLog())
        once += _conversation()[1:]
        twice = compact.compact(once, llm, StubLog())
        assert llm.requests[1][1]["content"].startswith("<transcript>\nUSER: " + SUMMARY)
        assert sum(1 for m in twice if (m.get("content") or "").startswith(SUMMARY)) == 1
