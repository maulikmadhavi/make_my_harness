"""Tests for ui — ANSI helpers must pass text through untouched when
styling is disabled (non-TTY, NO_COLOR) and wrap correctly when enabled."""

from make_harness import ui


def test_disabled_passthrough(monkeypatch):
    monkeypatch.setattr(ui, "ENABLED", False)
    assert ui.bold("x") == "x"
    assert ui.dim("x") == "x"
    assert ui.red("x") == "x"


def test_enabled_wraps_and_resets(monkeypatch):
    monkeypatch.setattr(ui, "ENABLED", True)
    assert ui.cyan("hello") == "\033[36mhello\033[0m"
    assert ui.bold("hi").endswith("\033[0m")


def test_pytest_capture_counts_as_non_tty():
    # Under pytest's captured stdout ENABLED must have come out False, so
    # every loop/policy print in the other tests stayed plain text.
    assert ui.ENABLED is False
