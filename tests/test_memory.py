"""Tests for toolsets.memory._slug — memory filenames must be safe and
never empty."""

from make_harness.toolsets.memory import _slug


def test_slug_basic():
    assert _slug("Pixi and Shell Quirks") == "pixi-and-shell-quirks"


def test_slug_collapses_special_characters():
    assert _slug("GROQ_API key!! (2026)") == "groq-api-key-2026"


def test_slug_never_empty():
    assert _slug("") == "memory"
    assert _slug("???") == "memory"
