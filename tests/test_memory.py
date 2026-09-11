"""Tests for toolsets.memory — _slug (filenames must be safe and never
empty) and the save_memory / read_memory / memory_index round trip
against a temp memory/ directory."""

import pytest

from make_harness.toolsets import memory
from make_harness.toolsets.memory import _slug, memory_index, read_memory, save_memory


def test_slug_basic():
    assert _slug("Pixi and Shell Quirks") == "pixi-and-shell-quirks"


def test_slug_collapses_special_characters():
    assert _slug("GROQ_API key!! (2026)") == "groq-api-key-2026"


def test_slug_never_empty():
    assert _slug("") == "memory"
    assert _slug("???") == "memory"


# --- save/read round trip against a temp memory/ directory -----------------

@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    d = tmp_path / "memory"
    monkeypatch.setattr(memory, "MEMORY_DIR", d)
    monkeypatch.setattr(memory, "INDEX", d / "MEMORY.md")
    return d


def test_index_is_empty_before_anything_is_saved(memory_dir):
    assert memory_index() == ""


def test_save_writes_the_file_and_an_index_line(memory_dir):
    out = save_memory("Favorite Editor", "VS Code\nwith vim keybindings")
    assert out == f"Saved memory 'Favorite Editor' to {memory_dir / 'favorite-editor.md'}"
    assert (memory_dir / "favorite-editor.md").read_text(encoding="utf-8") == "VS Code\nwith vim keybindings"
    assert memory_index() == "- [Favorite Editor](favorite-editor.md) — VS Code\n"


def test_read_resolves_the_name_through_the_same_slug(memory_dir):
    save_memory("Favorite Editor", "VS Code")
    assert read_memory("Favorite Editor") == "VS Code"
    assert read_memory("favorite editor") == "VS Code"
    assert read_memory("favorite-editor") == "VS Code"


def test_resave_updates_content_without_duplicating_the_index_line(memory_dir):
    save_memory("Editor", "VS Code")
    save_memory("Editor", "Neovim")
    assert read_memory("Editor") == "Neovim"
    assert memory_index().count("(editor.md)") == 1


def test_index_hook_is_the_first_line_capped_at_80_chars(memory_dir):
    save_memory("Long", "  " + "h" * 200 + "\nsecond line")
    hook = memory_index().split(" — ", 1)[1].rstrip("\n")
    assert hook == "h" * 80


def test_read_unknown_memory_is_a_clean_error(memory_dir):
    assert read_memory("nothing here") == "Error: no memory named 'nothing here'"
