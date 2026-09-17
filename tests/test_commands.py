"""Tests for commands.run — /clear, /compact, /sessions, /rewind and /exit,
and the unknown-command fallback, all offline (stub log, LLM and chooser,
sessions in a temp directory; no network or terminal needed)."""

import pytest
from helpers import StubLLM, StubLog

from make_harness import commands, config, history
from make_harness.commands import Context
from make_harness.session import Session, load


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
    new_messages, output = commands.run(line, messages, Context(log=StubLog()))
    assert new_messages == [messages[0]]
    assert "cleared" in output.lower()


def test_clear_logs_a_command_event():
    log = StubLog()
    commands.run("/clear", _messages(), Context(log=log))
    kind, fields = log.events[0]
    assert (kind, fields["name"]) == ("command", "clear")
    assert "cleared" in fields["output"].lower()


@pytest.mark.parametrize("line", ["/exit", "/exit now"], ids=["bare", "with-arguments"])
def test_exit_returns_none_so_the_repl_stops(line):
    log = StubLog()
    new_messages, output = commands.run(line, _messages(), Context(log=log))
    assert new_messages is None
    assert output == "Goodbye."
    assert log.events == [("command", {"name": "exit", "output": "Goodbye."})]


@pytest.mark.parametrize("line", ["/nope", "/"], ids=["unknown-name", "bare-slash"])
def test_unknown_command_is_inert(line):
    messages = _messages()
    log = StubLog()
    new_messages, output = commands.run(line, messages, Context(log=log))
    assert new_messages is messages  # untouched
    assert output.startswith(f"Unknown command: {line.split()[0]}")
    assert "/clear" in output  # lists what's actually available
    assert log.events == []  # nothing logged


def test_a_new_command_registers_through_the_decorator(sandboxed_registry):
    @commands.command
    def shout(messages, ctx):
        """Test-only command."""
        return messages + [{"role": "user", "content": "LOUD"}], "shouted"

    log = StubLog()
    new_messages, output = commands.run("/shout now", _messages(), Context(log=log))
    assert output == "shouted"
    assert new_messages[-1] == {"role": "user", "content": "LOUD"}
    assert log.events == [("command", {"name": "shout", "output": "shouted"})]


def test_unknown_command_lists_every_registered_command_sorted(sandboxed_registry):
    def zebra(messages, ctx):
        return messages, "z"

    commands.command(zebra)
    _, output = commands.run("/nope", _messages(), Context(log=StubLog()))
    assert output.endswith("available: /clear, /compact, /exit, /rewind, /sessions, /zebra")


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
    new_messages, output = commands.run("/compact", messages, Context(log=log, llm=StubLLM()))
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
    new_messages, output = commands.run("/compact", messages, Context(log=log, llm=FailingLLM()))
    assert new_messages is messages
    assert messages == _long_conversation()
    assert output.startswith("Compaction failed, conversation unchanged: RuntimeError")
    assert log.kinds() == ["command"]


def test_compact_on_a_short_conversation_needs_no_llm():
    messages = _messages()
    # Nothing is old enough to summarize, so llm=None must never be called.
    new_messages, output = commands.run("/compact", messages, Context(log=StubLog()))
    assert new_messages is messages
    assert output.startswith("Nothing old enough to compact yet")


def test_compact_reports_a_summary_that_came_out_no_smaller(small_window):
    class VerboseLLM(StubLLM):
        def complete(self, messages, tools=None):
            return {**super().complete(messages, tools), "content": "y" * 50_000}

    messages = _long_conversation()
    new_messages, output = commands.run("/compact", messages, Context(log=StubLog(), llm=VerboseLLM()))
    assert new_messages is messages
    assert output.startswith("The summary came out no smaller")


# --- sessions ---------------------------------------------------------------

def _chooser(*answers):
    """An ask() that returns scripted answers and records each prompt's choices."""
    seen = []
    answers = iter(answers)

    def ask(prompt_text, choices):
        seen.append(choices)
        return next(answers)

    return ask, seen


def _conversation(*questions):
    messages = [{"role": "system", "content": "old system prompt"}]
    for q in questions:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": f"re: {q}"}]
    return messages


def test_clear_moves_saving_to_a_new_session(tmp_path):
    store = Session(directory=tmp_path, session_id="before")
    store.save(_conversation("q1"))
    commands.run("/clear", _conversation("q1"), Context(log=StubLog(), session=store))
    assert store.id != "before"
    assert load(tmp_path / "before.jsonl") == _conversation("q1")


def test_compact_records_the_replacement_in_the_session(small_window, tmp_path):
    store = Session(directory=tmp_path, session_id="s")
    messages = _long_conversation()
    store.save(messages)
    new_messages, _ = commands.run("/compact", messages, Context(log=StubLog(), llm=StubLLM(), session=store))
    assert load(store.path) == new_messages


def test_sessions_opens_the_chosen_chat_with_the_current_system_prompt(tmp_path):
    Session(directory=tmp_path, session_id="20260101-000000-aaaa").save(_conversation("old question"))
    current = Session(directory=tmp_path, session_id="current")
    current.save(_conversation("current question"))
    ask, seen = _chooser("1")
    ctx = Context(log=StubLog(), session=current, ask=ask, system_prompt="new system prompt")
    new_messages, output = commands.run("/sessions", _conversation("current question"), ctx)
    assert [label for _, label in seen[0]] == ["20260101-000000-aaaa  old question  (3 messages)", "Cancel"]
    assert current.id == "20260101-000000-aaaa"
    assert new_messages == [{"role": "system", "content": "new system prompt"}] + _conversation("old question")[1:]
    assert output.startswith("Opened 20260101-000000-aaaa (3 messages).")
    assert "you > old question" in output


def test_sessions_cancel_keeps_the_current_chat(tmp_path):
    Session(directory=tmp_path, session_id="other").save(_conversation("q"))
    current = Session(directory=tmp_path, session_id="current")
    messages = _conversation("mine")
    ask, _ = _chooser("cancel")
    new_messages, output = commands.run("/sessions", messages, Context(log=StubLog(), session=current, ask=ask))
    assert new_messages is messages
    assert current.id == "current"
    assert output == "Kept the current chat."


def test_sessions_with_nothing_else_saved(tmp_path):
    current = Session(directory=tmp_path, session_id="current")
    current.save(_conversation("mine"))
    messages = _conversation("mine")
    new_messages, output = commands.run("/sessions", messages, Context(log=StubLog(), session=current))
    assert (new_messages, output) == (messages, "No other saved chats for this project.")


def test_rewind_drops_the_chosen_message_and_everything_after(tmp_path):
    store = Session(directory=tmp_path, session_id="s")
    messages = _conversation("q1", "q2", "q3")
    store.save(messages)
    ask, seen = _chooser("2")  # newest first: 1 = q3, 2 = q2
    new_messages, output = commands.run("/rewind", messages, Context(log=StubLog(), session=store, ask=ask))
    assert [label for _, label in seen[0]] == ["q3", "q2", "q1", "Cancel"]
    assert new_messages == _conversation("q1")
    assert output == "Rewound to before: q2 (3 messages kept)."
    assert load(store.path) == _conversation("q1")


def test_rewind_skips_the_compaction_summary(tmp_path):
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": history.SUMMARY + "\nnote\n</summary>"},
        {"role": "user", "content": "q1"},
    ]
    ask, seen = _chooser("cancel")
    new_messages, output = commands.run("/rewind", messages, Context(log=StubLog(), ask=ask))
    assert [label for _, label in seen[0]] == ["q1", "Cancel"]
    assert (new_messages, output) == (messages, "Nothing rewound.")


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_interrupting_the_chooser_changes_nothing(exc):
    def ask(prompt_text, choices):
        raise exc

    messages = _conversation("q1")
    new_messages, output = commands.run("/rewind", messages, Context(log=StubLog(), ask=ask))
    assert (new_messages, output) == (messages, "Nothing rewound.")


def test_rewind_on_a_fresh_chat():
    messages = [{"role": "system", "content": "s"}]
    assert commands.run("/rewind", messages, Context(log=StubLog()))[1] == "Nothing to rewind yet."
