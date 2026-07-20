"""Tests for commands.run — the /clear slash command and the unknown-
command fallback, both offline (a stub log, no LLM or terminal needed)."""

from make_harness import commands


class StubLog:
    def __init__(self):
        self.events = []

    def event(self, kind, **fields):
        self.events.append((kind, fields))


def _messages():
    return [
        {"role": "system", "content": "sys prompt + memory/skills index"},
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]


def test_clear_keeps_only_the_system_message():
    messages = _messages()
    new_messages, output = commands.run("/clear", messages, StubLog())
    assert new_messages == [messages[0]]
    assert "cleared" in output.lower()


def test_clear_logs_a_command_event():
    log = StubLog()
    commands.run("/clear", _messages(), log)
    assert log.events == [("command", {"name": "clear", "output": log.events[0][1]["output"]})]
    assert "cleared" in log.events[0][1]["output"].lower()


def test_clear_tolerates_trailing_arguments():
    messages = _messages()
    new_messages, _ = commands.run("/clear please", messages, StubLog())
    assert new_messages == [messages[0]]


def test_unknown_command_leaves_messages_untouched():
    messages = _messages()
    new_messages, output = commands.run("/nope", messages, StubLog())
    assert new_messages is messages
    assert "Unknown command: /nope" in output
    assert "/clear" in output  # lists what's actually available


def test_bare_slash_is_treated_as_unknown():
    messages = _messages()
    new_messages, output = commands.run("/", messages, StubLog())
    assert new_messages is messages
    assert output.startswith("Unknown command: /")


def test_unknown_command_does_not_log():
    log = StubLog()
    commands.run("/nope", _messages(), log)
    assert log.events == []
