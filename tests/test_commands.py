"""Tests for commands.run — the /clear slash command and the unknown-
command fallback, both offline (a stub log, no LLM or terminal needed)."""

import pytest
from helpers import StubLog

from make_harness import commands


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
    def shout(messages):
        """Test-only command."""
        return messages + [{"role": "user", "content": "LOUD"}], "shouted"

    log = StubLog()
    new_messages, output = commands.run("/shout now", _messages(), log)
    assert output == "shouted"
    assert new_messages[-1] == {"role": "user", "content": "LOUD"}
    assert log.events == [("command", {"name": "shout", "output": "shouted"})]


def test_unknown_command_lists_every_registered_command_sorted(sandboxed_registry):
    def zebra(messages):
        return messages, "z"

    commands.command(zebra)
    _, output = commands.run("/nope", _messages(), StubLog())
    assert output.endswith("available: /clear, /zebra")
