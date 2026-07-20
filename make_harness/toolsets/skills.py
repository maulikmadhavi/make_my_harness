"""Skill packages: skills/<name>/SKILL.md, discovered at REPL startup.

A skill is a markdown file with two frontmatter fields (name,
description) and a body of instructions — the same shape Claude Code
itself uses. Like memory (Stage 4), only the index (name + description)
is injected into the system prompt at startup — progressive disclosure —
so an unused skill costs a couple of index lines, not its whole body;
load_skill fetches the full instructions on demand.
"""

import re
from pathlib import Path

from make_harness.tools import tool

SKILLS_DIR = Path("skills")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def _parse(path):
    """Return (name, description, body) for one SKILL.md, or None if it
    has no valid --- frontmatter block."""
    m = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    header, body = m.groups()
    meta = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    name = meta.get("name") or path.parent.name
    return name, meta.get("description", ""), body.strip()


def discover():
    """Return {name: (description, body)} for every skills/*/SKILL.md."""
    if not SKILLS_DIR.is_dir():
        return {}
    skills = {}
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        parsed = _parse(skill_md)
        if parsed:
            name, description, body = parsed
            skills[name] = (description, body)
    return skills


def skills_index():
    return "\n".join(f"- {name}: {description}" for name, (description, _) in discover().items())


@tool
def load_skill(name: str) -> str:
    """Load the full instructions for a skill by name (see the skills index)."""
    skills = discover()
    if name not in skills:
        return f"Error: no skill named '{name}'"
    return skills[name][1]
