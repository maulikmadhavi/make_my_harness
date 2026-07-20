"""Tests for prompt.AtPathCompleter (the @path picker) and ChoiceCompleter
/_match_choice/make_chooser (the yes/no/always/deny dropdown), all driven
offline via prompt_toolkit Documents or a stubbed input() — no terminal
needed."""

import os

import pytest
from prompt_toolkit.document import Document

from make_harness.prompt import (
    AtPathCompleter,
    ChoiceCompleter,
    _match_choice,
    make_chooser,
    make_input,
)


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


_YNAD = [
    ("yes", "Yes — allow this call"),
    ("no", "No — deny this call"),
    ("always", "Always — allow forever"),
    ("deny", "Deny — block forever"),
]


def test_choice_completer_lists_everything_when_untyped():
    values = [c.text for c in ChoiceCompleter(_YNAD).get_completions(Document(""), None)]
    assert values == ["yes", "no", "always", "deny"]


def test_choice_completer_filters_by_value_prefix():
    values = [c.text for c in ChoiceCompleter(_YNAD).get_completions(Document("al"), None)]
    assert values == ["always"]


def test_choice_completer_filters_by_label_prefix():
    values = [c.text for c in ChoiceCompleter(_YNAD).get_completions(Document("Deny"), None)]
    assert values == ["deny"]


def test_match_choice_exact_value():
    assert _match_choice("yes", [("yes", "Y"), ("no", "N")]) == "yes"


def test_match_choice_case_insensitive_label():
    choices = [("always", "Always Allow"), ("no", "No")]
    assert _match_choice("ALWAYS ALLOW", choices) == "always"


def test_match_choice_unambiguous_prefix():
    assert _match_choice("al", [("yes", "Y"), ("always", "Always")]) == "always"


def test_match_choice_ambiguous_prefix_returns_none():
    assert _match_choice("de", [("deny", "Deny"), ("delete", "Delete")]) is None


def test_match_choice_no_match_returns_none():
    assert _match_choice("maybe", [("yes", "Y"), ("no", "N")]) is None


def test_match_choice_empty_returns_none():
    assert _match_choice("", [("yes", "Y")]) is None


def test_chooser_non_tty_matches_typed_value(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "always")
    ask = make_chooser()
    assert ask("allow? ", _YNAD) == "always"


def test_chooser_non_tty_reprompts_until_matched(monkeypatch):
    responses = iter(["banana", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))
    ask = make_chooser()
    assert ask("allow? ", _YNAD) == "yes"
