"""Late injection: a small block added to the end of every request.

The block is rebuilt for each request and never saved in the transcript. It
sits after everything the server may have cached, so it costs no cache hits,
and the transcript's own prefix never changes because of it.

  <env>                date and time, git branch
  <system-reminder>    files git sees changing between the agent's turns

ChangeTracker takes a snapshot when a turn ends and compares against it
when the next one starts, so the agent hears about edits made by someone
else between turns — never about its own.
"""

import subprocess
from datetime import datetime
from pathlib import Path

LABELS = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "??": "new", "": "committed or reverted"}


def git(*args):
    """stdout of a git command, or None outside a repository or without git."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def branch():
    out = git("branch", "--show-current")
    if out is None:
        return "(not a git repository)"
    return out.strip() or "(detached HEAD)"


def git_state():
    """path -> (status code, size, mtime) for every file git reports as
    changed. Size and mtime rather than a content hash: this runs every
    turn, and a changed file may be large."""
    out = git("status", "--porcelain=v1", "-z")
    root = git("rev-parse", "--show-toplevel")
    if out is None or root is None:
        return {}
    state = {}
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        code, path = entry[:2].strip(), entry[3:]
        if code[:1] in ("R", "C"):
            next(entries, None)  # -z puts a rename's original path in the next field
        try:
            stat = (Path(root.strip()) / path).stat()
            state[path] = (code, stat.st_size, stat.st_mtime_ns)
        except OSError:
            state[path] = (code, None, None)
    return state


class ChangeTracker:
    """Which files changed between the agent's turns."""

    def __init__(self):
        self.last = None

    def snapshot(self):
        """Call when a turn ends, after the agent's own edits."""
        self.last = git_state()

    def changes(self):
        """{path: label} for files whose status or contents moved since the
        last snapshot. Empty before the first snapshot."""
        now = git_state()
        if self.last is None:
            return {}
        changed = {path: LABELS.get(v[0], v[0]) for path, v in now.items() if self.last.get(path) != v}
        changed.update({path: LABELS[""] for path in self.last if path not in now})
        return changed


def reminder(branch_name, changed=None):
    """The text of the block for one request."""
    lines = ["<env>", f"date: {datetime.now():%Y-%m-%d %H:%M}", f"git branch: {branch_name}", "</env>"]
    if changed:
        lines += ["<system-reminder>", "These files changed since your last turn. Read them again before editing:"]
        lines += [f"{label}: {path}" for path, label in changed.items()]
        lines.append("</system-reminder>")
    return "\n".join(lines)


def with_reminder(messages, block):
    """A copy of `messages` ready to send, with the block at the end: merged
    into a trailing user message, so roles keep alternating for chat templates
    that insist on it, or else appended as its own user message."""
    last = messages[-1] if messages else None
    if last and last["role"] == "user" and isinstance(last.get("content"), str):
        return messages[:-1] + [{**last, "content": f"{last['content']}\n\n{block}"}]
    return messages + [{"role": "user", "content": block}]
