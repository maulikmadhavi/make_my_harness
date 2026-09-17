"""Skill packages: <dir>/<name>/SKILL.md, discovered at REPL startup.

Two directories are searched, and the project wins a name clash:
  ./.agents/skills     skills that ship with the project
  ~/.agents/skills     your own, available in every project

A skill is a markdown file with YAML frontmatter (name, description) and a
body of instructions — the same shape Claude Code itself uses. Like memory
(Stage 4), only the index (name + description) is injected into the system
prompt at startup — progressive disclosure — so an unused skill costs a
couple of index lines, not its whole body; load_skill fetches the full
instructions on demand.
"""

import re
from pathlib import Path

import yaml

from make_harness.tools import tool

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def skill_dirs():
    return [Path(".agents") / "skills", Path.home() / ".agents" / "skills"]


def _frontmatter(header):
    """Parse the header as YAML; fall back to one `key: value` per line for
    headers YAML rejects, like an unquoted description containing ': '."""
    try:
        meta = yaml.safe_load(header)
    except yaml.YAMLError:
        meta = None
    if isinstance(meta, dict):
        return {key: " ".join(str(value).split()) for key, value in meta.items() if value is not None}
    meta = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def _parse(path):
    """Return (name, description, body) for one SKILL.md, or None if it
    has no valid --- frontmatter block."""
    m = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    header, body = m.groups()
    meta = _frontmatter(header)
    name = meta.get("name") or path.parent.name
    return name, meta.get("description", ""), body.strip()


def discover():
    """Return {name: (description, body)} for every SKILL.md found."""
    skills = {}
    for directory in skill_dirs():
        for skill_md in sorted(directory.glob("*/SKILL.md")):
            parsed = _parse(skill_md)
            if parsed:
                name, description, body = parsed
                skills.setdefault(name, (description, body))
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
