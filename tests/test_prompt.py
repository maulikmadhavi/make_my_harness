"""Tests for prompt.AtPathCompleter — the @path picker's completion logic,
driven offline via prompt_toolkit Documents (no terminal needed)."""

import os

import pytest
from prompt_toolkit.document import Document

from make_harness.prompt import AtPathCompleter, make_input


def _completions(text):
    return [c.text for c in AtPathCompleter().get_completions(Document(text), None)]


def _setup_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("r", encoding="utf-8")
    (tmp_path / "data.py").write_text("d", encoding="utf-8")
    (tmp_path / "app.py").write_text("a", encoding="utf-8")
    (tmp_path / ".hidden").write_text("h", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()


def test_plain_text_gets_no_completions(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert _completions("explain the code") == []
    assert _completions("a sentence ending in d") == []


def test_bare_at_lists_folders_first_then_files(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert _completions("look at @") == ["docs/", "app.py", "data.py"]


def test_prefix_filters_case_insensitively(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert _completions("@D") == ["docs/", "data.py"]
    assert _completions("@app") == ["app.py"]


def test_nested_segment_completion(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert _completions("read @docs/r") == ["docs/readme.md"]


def test_hidden_and_noise_entries_are_skipped(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    everything = _completions("@")
    assert ".hidden" not in everything
    assert "__pycache__/" not in everything


def test_replaces_the_whole_token(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    doc = Document("see @docs/r")
    completion = next(iter(AtPathCompleter().get_completions(doc, None)))
    assert completion.start_position == -len("docs/r")


@pytest.mark.skipif(os.name != "nt", reason="backslash separators are Windows-style")
def test_backslash_separator(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert _completions("read @docs\\r") == ["docs\\readme.md"]


def test_non_tty_falls_back_to_plain_input():
    # Under pytest stdin/stdout are captured, so make_input must return the
    # builtin — the piped-REPL regression test covers this end to end.
    assert make_input() is input
