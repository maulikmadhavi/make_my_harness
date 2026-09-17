"""Tests for the terminal I/O layer: ui's ANSI helpers, prompt's @path
picker (AtPathCompleter) and the choice dropdown (ChoiceCompleter,
_match_choice, make_chooser).

All offline — completers are driven with prompt_toolkit Documents and
the chooser with a stubbed input(), so no terminal is needed.
"""

import os

import pytest
from prompt_toolkit.document import Document

from make_harness import prompt, ui
from make_harness.prompt import (
    AtPathCompleter,
    ChoiceCompleter,
    _match_choice,
    make_chooser,
    make_input,
)


class TestAnsiHelpers:
    def test_disabled_passes_text_through(self, monkeypatch):
        monkeypatch.setattr(ui, "ENABLED", False)
        assert (ui.bold("x"), ui.dim("x"), ui.yellow("x")) == ("x", "x", "x")

    def test_enabled_wraps_and_resets(self, monkeypatch):
        monkeypatch.setattr(ui, "ENABLED", True)
        assert ui.cyan("hello") == "\033[36mhello\033[0m"
        assert ui.bold("hi").endswith("\033[0m")

    def test_pytest_capture_counts_as_non_tty(self):
        # Under pytest's captured stdout ENABLED must have come out False, so
        # every loop/policy print in the other tests stayed plain text, and
        # make_input must hand back the builtin rather than a PromptSession.
        assert ui.ENABLED is False
        assert make_input() is input


def test_terminal_input_keeps_history_under_home_agents(tmp_path, monkeypatch):
    # A real PromptSession needs a console, so record its arguments instead.
    captured = {}
    monkeypatch.setattr(prompt.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(prompt.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(prompt, "PromptSession", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(prompt, "history_path", lambda: tmp_path / ".agents" / "history")
    make_input()
    assert captured["history"].filename == str(tmp_path / ".agents" / "history")
    assert (tmp_path / ".agents").is_dir()  # created so the first save succeeds


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A temp cwd holding a folder, two files, and two entries the
    completer must skip."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("r", encoding="utf-8")
    (tmp_path / "data.py").write_text("d", encoding="utf-8")
    (tmp_path / "app.py").write_text("a", encoding="utf-8")
    (tmp_path / ".hidden").write_text("h", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    return tmp_path


def _completions(text):
    return [c.text for c in AtPathCompleter().get_completions(Document(text), None)]


class TestAtPathCompleter:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("explain the code", []),
            ("a sentence ending in d", []),
            ("look at @", ["docs/", "app.py", "data.py"]),  # folders first, then alphabetical
            ("@D", ["docs/", "data.py"]),  # case-insensitive prefix
            ("@app", ["app.py"]),
            ("read @docs/r", ["docs/readme.md"]),
            ("@nowhere/", []),  # missing folder
        ],
        ids=["plain-text", "trailing-word", "bare-at", "case-insensitive",
             "file-prefix", "nested-segment", "missing-folder"],
    )
    def test_completions(self, tree, text, expected):
        assert _completions(text) == expected

    def test_hidden_and_noise_entries_are_skipped(self, tree):
        everything = _completions("@")
        assert ".hidden" not in everything
        assert "__pycache__/" not in everything

    def test_replaces_the_whole_token(self, tree):
        completion = next(iter(AtPathCompleter().get_completions(Document("see @docs/r"), None)))
        assert completion.start_position == -len("docs/r")

    @pytest.mark.skipif(os.name != "nt", reason="backslash separators are Windows-style")
    def test_backslash_separator(self, tree):
        assert _completions("read @docs\\r") == ["docs\\readme.md"]


_YNAD = [
    ("yes", "Yes — allow this call"),
    ("no", "No — deny this call"),
    ("always", "Always — allow forever"),
    ("deny", "Deny — block forever"),
]


class TestChoiceCompleter:
    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("", ["yes", "no", "always", "deny"]),
            ("al", ["always"]),  # value prefix
            ("Deny", ["deny"]),  # label prefix, case-insensitive
        ],
        ids=["untyped-lists-all", "value-prefix", "label-prefix"],
    )
    def test_filtering(self, typed, expected):
        assert [c.text for c in ChoiceCompleter(_YNAD).get_completions(Document(typed), None)] == expected

    def test_replaces_everything_typed(self):
        completions = list(ChoiceCompleter(_YNAD).get_completions(Document("  alw"), None))
        assert [c.text for c in completions] == ["always"]
        assert completions[0].start_position == -len("  alw")


class TestMatchChoice:
    @pytest.mark.parametrize(
        "raw,choices,expected",
        [
            ("yes", [("yes", "Y"), ("no", "N")], "yes"),
            ("ALWAYS ALLOW", [("always", "Always Allow"), ("no", "No")], "always"),
            ("al", [("yes", "Y"), ("always", "Always")], "always"),
            ("de", [("deny", "Deny"), ("delete", "Delete")], None),
            ("maybe", [("yes", "Y"), ("no", "N")], None),
            ("", [("yes", "Y")], None),
        ],
        ids=["exact-value", "case-insensitive-label", "unambiguous-prefix",
             "ambiguous-prefix", "no-match", "empty"],
    )
    def test_match(self, raw, choices, expected):
        assert _match_choice(raw, choices) == expected


class TestChooserFallback:
    """Off-terminal make_chooser() falls back to a typed prompt."""

    def test_matches_a_typed_value(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda prompt: "always")
        assert make_chooser()("allow? ", _YNAD) == "always"

    def test_reprompts_until_matched(self, monkeypatch):
        responses = iter(["banana", "y"])
        monkeypatch.setattr("builtins.input", lambda prompt: next(responses))
        assert make_chooser()("allow? ", _YNAD) == "yes"

    def test_a_numbered_list_prints_its_labels(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda prompt: "2")
        choices = [("1", "newest chat"), ("2", "older chat"), ("cancel", "Cancel")]
        assert make_chooser()("open chat: ", choices) == "2"
        assert capsys.readouterr().out == "  1) newest chat\n  2) older chat\n  cancel) Cancel\n"

    def test_named_choices_print_no_list(self, monkeypatch, capsys):
        monkeypatch.setattr("builtins.input", lambda prompt: "yes")
        make_chooser()("allow? ", _YNAD)
        assert capsys.readouterr().out == ""
