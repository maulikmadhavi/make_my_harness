"""Tests for session — the append-only transcript file, its replay, the
per-project directory, and the listing and preview /sessions shows."""

import json
import os
import time

import pytest

from make_harness import session
from make_harness.session import Session, load, preview, title


def _msgs(*contents):
    """system, then alternating user/assistant messages."""
    out = [{"role": "system", "content": "sys"}]
    for i, content in enumerate(contents):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": content})
    return out


@pytest.fixture
def store(tmp_path):
    return Session(directory=tmp_path, session_id="s1")


def _lines(store):
    return [json.loads(line) for line in store.path.read_text(encoding="utf-8").splitlines()]


class TestSaveAndLoad:
    def test_nothing_is_written_until_there_is_something_to_save(self, store):
        store.save([])
        assert not store.path.exists()

    def test_save_appends_only_new_messages(self, store):
        messages = _msgs("q1", "a1")
        store.save(messages)
        messages += _msgs("q2")[1:]
        store.save(messages)
        store.save(messages)  # nothing new: nothing written
        assert _lines(store) == messages
        assert load(store.path) == messages

    def test_rewind_is_recorded_and_the_old_lines_stay(self, store):
        messages = _msgs("q1", "a1", "q2", "a2")
        store.save(messages)
        store.rewind_to(3)
        kept = messages[:3] + [{"role": "assistant", "content": "a1-again"}]
        store.save(kept)
        assert load(store.path) == kept
        assert {"rewind_to": 3} in _lines(store)
        assert messages[4] in _lines(store)  # the dropped answer is still in the file

    def test_replace_is_recorded(self, store):
        store.save(_msgs("q1", "a1", "q2"))
        compacted = _msgs("<summary>note</summary>")
        store.replace(compacted)
        store.save(compacted + [{"role": "assistant", "content": "a2"}])
        assert load(store.path) == compacted + [{"role": "assistant", "content": "a2"}]

    def test_a_half_written_last_line_is_skipped(self, store):
        store.save(_msgs("q1"))
        with store.path.open("a", encoding="utf-8") as f:
            f.write('{"role": "assistant", "cont')
        assert load(store.path) == _msgs("q1")

    def test_unicode_round_trips(self, store):
        store.save(_msgs("naïve — 日本語"))
        assert load(store.path)[1]["content"] == "naïve — 日本語"


class TestSwitching:
    def test_open_resumes_appending_after_the_loaded_messages(self, tmp_path):
        first = Session(directory=tmp_path, session_id="a")
        first.save(_msgs("q1", "a1"))
        other = Session(directory=tmp_path, session_id="b")
        messages = other.open("a")
        assert (other.id, other.written, messages) == ("a", 3, _msgs("q1", "a1"))
        other.save(messages + [{"role": "user", "content": "q2"}])
        assert load(tmp_path / "a.jsonl")[-1] == {"role": "user", "content": "q2"}

    def test_start_new_writes_to_a_fresh_file(self, store):
        store.save(_msgs("q1"))
        old_path = store.path
        store.start_new()
        assert store.path != old_path
        store.save(_msgs("fresh"))
        assert load(store.path) == _msgs("fresh")
        assert load(old_path) == _msgs("q1")

    def test_list_is_newest_first_with_titles(self, tmp_path):
        older = Session(directory=tmp_path, session_id="older")
        older.save(_msgs("first chat"))
        newer = Session(directory=tmp_path, session_id="newer")
        newer.save(_msgs("second chat", "reply"))
        past = time.time() - 60
        os.utime(older.path, (past, past))
        assert newer.list() == [
            {"id": "newer", "title": "second chat", "messages": 3},
            {"id": "older", "title": "first chat", "messages": 2},
        ]

    def test_list_without_a_directory_is_empty(self, tmp_path):
        assert Session(directory=tmp_path / "missing").list() == []


def test_sessions_are_kept_per_project_under_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "my project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(project)
    directory = session.sessions_dir()
    assert directory.parent == home / ".agents" / "sessions"
    assert directory.name.endswith("my-project")
    assert all(c.isalnum() or c == "-" for c in directory.name)  # safe on Windows: no ':' or '\\'


class TestTitleAndPreview:
    def test_title_is_the_first_user_message_without_attachments(self):
        messages = _msgs("Explain   @a.py\n\n[Attached file a.py]\nprint(1)")
        assert title(messages) == "Explain @a.py"

    def test_title_of_an_empty_chat(self):
        assert title(_msgs()) == "(empty)"

    def test_preview_shows_turns_tool_calls_and_compaction(self):
        messages = _msgs("<summary>\nnote\n</summary>", "ok", "read it")
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ]})
        messages.append({"role": "tool", "tool_call_id": "c1", "content": "file text"})
        messages.append({"role": "assistant", "content": "It says hi."})
        assert preview(messages) == (
            "  (earlier conversation compacted)\n"
            "  agent > ok\n"
            "  you > read it\n"
            "    → read_file\n"
            "  agent > It says hi."
        )
