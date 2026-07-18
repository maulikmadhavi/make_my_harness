"""Persistent memory: one markdown file per fact + a MEMORY.md index.

The index is injected into the system prompt at REPL start so the agent
always knows what it remembers; individual files are read on demand
(progressive disclosure).
"""

import re
from pathlib import Path

from harness.tools import tool

MEMORY_DIR = Path("memory")
INDEX = MEMORY_DIR / "MEMORY.md"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "memory"


@tool
def save_memory(name: str, content: str) -> str:
    """Save a fact to persistent memory so future sessions can recall it.

    name is a short title; content is the fact itself.
    """
    MEMORY_DIR.mkdir(exist_ok=True)
    slug = _slug(name)
    path = MEMORY_DIR / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    hook = content.strip().splitlines()[0][:80]
    existing = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    if f"({slug}.md)" not in existing:
        with INDEX.open("a", encoding="utf-8") as f:
            f.write(f"- [{name}]({slug}.md) — {hook}\n")
    return f"Saved memory '{name}' to {path}"


@tool
def read_memory(name: str) -> str:
    """Read a fact from persistent memory by its name (see the memory index)."""
    path = MEMORY_DIR / f"{_slug(name)}.md"
    if not path.exists():
        return f"Error: no memory named '{name}'"
    return path.read_text(encoding="utf-8")


def memory_index():
    return INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
