"""Tiny ANSI styling helpers for the REPL — stdlib only, no rich/colorama.

Styling is disabled when stdout is not a TTY or NO_COLOR is set
(https://no-color.org), so piped output and logs stay clean. On Windows,
one os.system("") call switches the classic console into VT mode;
Windows Terminal understands ANSI escapes out of the box.
"""

import os
import sys

ENABLED = sys.stdout.isatty() and not os.getenv("NO_COLOR")

if ENABLED and os.name == "nt":
    os.system("")  # enables ANSI escape processing in the legacy console


def _wrap(code, text):
    return f"\033[{code}m{text}\033[0m" if ENABLED else text


def bold(text):
    return _wrap("1", text)


def dim(text):
    return _wrap("2", text)


def red(text):
    return _wrap("31", text)


def green(text):
    return _wrap("32", text)


def yellow(text):
    return _wrap("33", text)


def cyan(text):
    return _wrap("36", text)
