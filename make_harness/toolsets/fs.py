from pathlib import Path

from make_harness.tools import tool

MAX_LINES = 2000
MAX_CHARS = 10_000  # same inline budget as history.CAP


@tool
def read_file(path: str, offset: int = 1, limit: int = MAX_LINES) -> str:
    """Read a text file and return its contents with line numbers. offset is the first line to read (1-based) and limit the most lines to return; use them to page through a long file."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset, 1) - 1
    out, size = [], 0
    # Stop at whichever comes first: `limit` lines or MAX_CHARS characters.
    # Cutting on a line boundary means the next page starts exactly where
    # this one stopped.
    for number, line in enumerate(lines[start : start + max(limit, 1)], start + 1):
        entry = f"{number}\t{line}"
        if out and size + len(entry) > MAX_CHARS:
            break
        out.append(entry)
        size += len(entry) + 1
    if not out:
        return "[empty file]" if not lines else f"[no lines at offset {offset}: the file has {len(lines)} lines]"
    remaining = len(lines) - (start + len(out))
    if remaining > 0:
        out.append(f"[not the end of the file: {remaining} more lines — continue with offset={start + len(out) + 1}]")
    return "\n".join(out)


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed. Overwrites existing files."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {p}"


@tool
def str_replace(path: str, old_str: str, new_str: str, allow_multi_edit: bool = False) -> str:
    """Replace exact text in a file. old_str must appear exactly once, so include surrounding lines to make it unique; set allow_multi_edit to replace every match instead. Copy old_str from the file itself, without the line-number prefixes read_file adds."""
    if not old_str:
        return "Error: old_str is empty. Use write_file to create a file."
    p = Path(path)
    # newline="" reads the line endings exactly as they are on disk. A CRLF
    # file is matched and edited in CRLF, so an edit made on Windows (or to a
    # Windows file) never rewrites the endings of the lines it didn't touch.
    with p.open(encoding="utf-8", newline="") as f:
        text = f.read()
    if "\r\n" in text:
        old_str, new_str = (s.replace("\r\n", "\n").replace("\n", "\r\n") for s in (old_str, new_str))
    count = text.count(old_str)
    if count == 0:
        return f"Error: old_str was not found in {path}. Read the file again; it may have changed."
    if count > 1 and not allow_multi_edit:
        return (
            f"Error: old_str matches {count} times in {path}. Include surrounding lines "
            "to make it unique, or set allow_multi_edit to replace every match."
        )
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write(text.replace(old_str, new_str))
    return f"Replaced {count} match{'es' if count > 1 else ''} in {path}"
