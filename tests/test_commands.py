"""Tests for commands.run — the /clear, /compact and /exit slash commands
and the unknown-command fallback, all offline (stub log and LLM, no network
or terminal needed)."""

import pytest
from helpers import StubLLM, StubLog

from make_harness import commands, config, history


def _messages():
    return [
        {"role": "system", "content": "sys prompt + memory/skills index"},
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]


@pytest.fixture
def sandboxed_registry(monkeypatch):
    """A copy of the command registry, so a test-only command can be
    registered without leaking into the rest of the run."""
    monkeypatch.setattr(commands, "_COMMANDS", dict(commands._COMMANDS))


@pytest.mark.parametrize("line", ["/clear", "/clear please"], ids=["bare", "with-arguments"])
def test_clear_keeps_only_the_system_message(line):
    messages = _messages()
    new_messages, output = commands.run(line, messages, StubLog())
    assert new_messages == [messages[0]]
    assert "cleared" in output.lower()


def test_clear_logs_a_command_event():
    log = StubLog()
    commands.run("/clear", _messages(), log)
    kind, fields = log.events[0]
    assert (kind, fields["name"]) == ("command", "clear")
    assert "cleared" in fields["output"].lower()


@pytest.mark.parametrize("line", ["/exit", "/exit now"], ids=["bare", "with-arguments"])
def test_exit_returns_none_so_the_repl_stops(line):
    log = StubLog()
    new_messages, output = commands.run(line, _messages(), log)
    assert new_messages is None
    assert output == "Goodbye."
    assert log.events == [("command", {"name": "exit", "output": "Goodbye."})]


@pytest.mark.parametrize("line", ["/nope", "/"], ids=["unknown-name", "bare-slash"])
def test_unknown_command_is_inert(line):
    messages = _messages()
    log = StubLog()
    new_messages, output = commands.run(line, messages, log)
    assert new_messages is messages  # untouched
    assert output.startswith(f"Unknown command: {line.split()[0]}")
    assert "/clear" in output  # lists what's actually available
    assert log.events == []  # nothing logged


def test_a_new_command_registers_through_the_decorator(sandboxed_registry):
    @commands.command
    def shout(messages, llm, log):
        """Test-only command."""
        return messages + [{"role": "user", "content": "LOUD"}], "shouted"

    log = StubLog()
    new_messages, output = commands.run("/shout now", _messages(), log)
    assert output == "shouted"
    assert new_messages[-1] == {"role": "user", "content": "LOUD"}
    assert log.events == [("command", {"name": "shout", "output": "shouted"})]


def test_unknown_command_lists_every_registered_command_sorted(sandboxed_registry):
    def zebra(messages, llm, log):
        return messages, "z"

    commands.command(zebra)
    _, output = commands.run("/nope", _messages(), StubLog())
    assert output.endswith("available: /clear, /compact, /exit, /zebra")


@pytest.fixture
def small_window(monkeypatch):
    """A 1000-token window, so a few kilobytes of history is old enough to
    compact while staying under the automatic threshold."""
    monkeypatch.setattr(config, "CONTEXT_WINDOW", 1000)


def _long_conversation():
    """Turns of ~400 chars each: more than the ~350-token tail compaction
    keeps, so the oldest turns get summarized."""
    messages = [{"role": "system", "content": "sys prompt + memory/skills index"}]
    for i in range(6):
        messages += [
            {"role": "user", "content": f"turn {i} " + "q" * 400},
            {"role": "assistant", "content": f"answer {i} " + "a" * 400},
        ]
    return messages


def test_compact_summarizes_the_older_turns(small_window):
    messages = _long_conversation()
    log = StubLog()
    new_messages, output = commands.run("/compact", messages, log, StubLLM())
    assert new_messages[0] == messages[0]
    assert "SUMMARY OF OLDER CONVERSATION" in new_messages[1]["content"]
    assert new_messages[2:] == messages[-len(new_messages[2:]):]  # recent tail kept verbatim
    assert output.startswith("Compacted: ~")
    assert history.estimate(new_messages) < history.estimate(messages)
    assert log.kinds() == ["compaction", "command"]


def test_compact_failure_leaves_the_conversation_untouched(small_window):
    class FailingLLM:
        def complete(self, messages, tools=None):
            raise RuntimeError("context size exceeded")

    messages = _long_conversation()
    log = StubLog()
    new_messages, output = commands.run("/compact", messages, log, FailingLLM())
    assert new_messages is messages
    assert messages == _long_conversation()
    assert output.startswith("Compaction failed, conversation unchanged: RuntimeError")
    assert log.kinds() == ["command"]


def test_compact_on_a_short_conversation_needs_no_llm():
    messages = _messages()
    # Nothing is old enough to summarize, so llm=None must never be called.
    new_messages, output = commands.run("/compact", messages, StubLog())
    assert new_messages is messages
    assert output.startswith("Nothing old enough to compact yet")


def test_compact_reports_a_summary_that_came_out_no_smaller(small_window):
    class VerboseLLM(StubLLM):
        def complete(self, messages, tools=None):
            return {**super().complete(messages, tools), "content": "y" * 50_000}

    messages = _long_conversation()
    new_messages, output = commands.run("/compact", messages, StubLog(), VerboseLLM())
    assert new_messages is messages
    assert output.startswith("The summary came out no smaller")
