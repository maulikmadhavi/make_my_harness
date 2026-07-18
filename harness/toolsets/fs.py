from pathlib import Path

from harness.tools import tool

MAX_LINES = 2000


@tool
def read_file(path: str) -> str:
    """Read a text file and return its contents with line numbers."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    out = "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(lines[:MAX_LINES]))
    if len(lines) > MAX_LINES:
        out += f"\n[truncated: {len(lines) - MAX_LINES} more lines]"
    return out or "[empty file]"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed. Overwrites existing files."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {p}"
