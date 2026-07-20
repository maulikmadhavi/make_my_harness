"""Interactive input with a pop-up file picker for @path mentions.

Typing `@` (or `@par...`) opens a completion menu of files and folders
under the cursor — Tab/arrows to select, like the fancy harnesses.
Built on prompt_toolkit, the project's first real UI dependency: an
interactive menu is not feasible with the stdlib alone (readline doesn't
exist on Windows). When stdin/stdout isn't a terminal (piped input,
tests, CI) this falls back to plain input() and behaves exactly as
before.
"""

import re
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI

# Same token shape as mentions.py's _MENTION, anchored to the cursor.
_AT_TOKEN = re.compile(r"@([\w./\\:~-]*)$")
_SKIP = {"__pycache__", "node_modules", ".git"}


class AtPathCompleter(Completer):
    """Completes filesystem paths, but only inside an @mention token."""

    def get_completions(self, document, complete_event):
        m = _AT_TOKEN.search(document.text_before_cursor)
        if not m:
            return
        token = m.group(1)
        cut = max(token.rfind("/"), token.rfind("\\"))
        base, prefix = (token[: cut + 1], token[cut + 1 :]) if cut >= 0 else ("", token)
        directory = Path(base).expanduser() if base else Path(".")
        if not directory.is_dir():
            return
        entries = sorted(
            directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())
        )  # folders first, then files, alphabetical
        for entry in entries:
            name = entry.name
            if name in _SKIP or name.startswith("."):
                continue
            if not name.lower().startswith(prefix.lower()):
                continue
            display = name + ("/" if entry.is_dir() else "")
            yield Completion(
                base + display if entry.is_dir() else base + name,
                start_position=-len(token),
                display=display,
            )


def make_input():
    """Return a read(prompt_text) callable.

    A real terminal gets a PromptSession with the @path picker; anything
    else (piped stdin, tests) gets plain input(), same behavior as before.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return input
    session = PromptSession(completer=AtPathCompleter(), complete_while_typing=True)

    def read(prompt_text):
        return session.prompt(ANSI(prompt_text))

    return read
