"""Interactive input: a pop-up file picker for @path mentions, and a
pop-up dropdown for multiple-choice prompts (e.g. the permission gate).

Typing `@` (or `@par...`) opens a completion menu of files and folders
under the cursor — Tab/arrows to select, like the fancy harnesses.
Built on prompt_toolkit, the project's first real UI dependency: an
interactive menu is not feasible with the stdlib alone (readline doesn't
exist on Windows). When stdin/stdout isn't a terminal (piped input,
tests, CI) both fall back to plain input() and behave exactly as before.
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


class ChoiceCompleter(Completer):
    """Completes from a fixed (value, label) list, filtering on whatever
    has been typed so far (case-insensitive prefix on value or label)."""

    def __init__(self, choices):
        self.choices = choices

    def get_completions(self, document, complete_event):
        typed = document.text_before_cursor.strip().lower()
        for value, label in self.choices:
            if not typed or value.lower().startswith(typed) or label.lower().startswith(typed):
                yield Completion(value, start_position=-len(document.text_before_cursor), display=label)


def _match_choice(raw, choices):
    """Resolve typed text to a choice value: exact value/label match, or
    an unambiguous value prefix. Returns None if nothing matched."""
    raw = raw.strip().lower()
    if not raw:
        return None
    for value, label in choices:
        if raw == value.lower() or raw == label.lower():
            return value
    prefix_matches = [value for value, _ in choices if value.lower().startswith(raw)]
    return prefix_matches[0] if len(prefix_matches) == 1 else None


def make_chooser():
    """Return an ask(prompt_text, choices) -> value callable.

    choices is a list of (value, label) pairs. In a real terminal this
    opens a pop-up dropdown (arrow keys or typing to filter, Enter to
    pick — the same picker mechanism as @path); otherwise it falls back
    to a plain typed prompt, matched against each choice's value/label.
    Re-prompts on anything that doesn't resolve to exactly one choice.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):

        def ask(prompt_text, choices):
            hint = "/".join(value for value, _ in choices)
            while True:
                matched = _match_choice(input(f"{prompt_text}[{hint}] "), choices)
                if matched:
                    return matched

        return ask

    session = PromptSession(complete_while_typing=True)

    def _open_menu():
        session.app.current_buffer.start_completion(select_first=False)

    def ask(prompt_text, choices):
        session.completer = ChoiceCompleter(choices)
        while True:
            matched = _match_choice(session.prompt(ANSI(prompt_text), pre_run=_open_menu), choices)
            if matched:
                return matched

    return ask
