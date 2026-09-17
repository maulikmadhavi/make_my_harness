"""Settings: the real environment first, then the first env file found.

Env files hold one KEY=value per line and are read from (first found wins):
  ./.env           the directory make-harness is launched from
  ~/.agents/env    the per-user default

A variable already set in the shell is never overridden, so
`MODEL=other make-harness` works for a one-off. MAKE_HARNESS_NO_ENV skips
the files entirely (the test suite sets it).

cli.py imports this module before anything else from the harness, so the
file is loaded once, before any module reads a setting at its own import.
"""

import os
from pathlib import Path

# Old names from before the switch to the OpenAI SDK, mapped to what
# replaces them — only used to say what to rename.
RENAMED = {
    "LLM_ENDPOINT": "BASE_URL",
    "LLM_MODEL": "MODEL",
    "LLM_API_KEY": "API_KEY",
    "GROQ_API_KEY": "API_KEY (with BASE_URL=https://api.groq.com/openai/v1)",
}


def env_files():
    return [Path(".env"), Path.home() / ".agents" / "env"]


def load_env_file():
    """Load the first readable env file, without overriding the real
    environment. Skipped entirely when MAKE_HARNESS_NO_ENV is set."""
    if os.getenv("MAKE_HARNESS_NO_ENV"):
        return
    for path in env_files():
        if not path.is_file():
            continue
        try:
            # utf-8-sig, not the locale encoding: a file written by Notepad or
            # PowerShell carries a BOM, which would otherwise be read as part
            # of the first key's name and silently drop that setting.
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and not os.getenv(key):
                os.environ[key] = value.strip().strip("\"'")
        return


load_env_file()

# How much room the model has, and how it is spent. CONTEXT_WINDOW is the
# context length the server actually loads the model with, in tokens —
# 8192 for a small local model, not the 128k it may advertise.
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "128000"))
COMPACT_AT = 0.85  # compact once a request crosses this share of the window
COMPACT_TO = 0.35  # keeping a recent tail this big, so it doesn't fire again next turn


def backend():
    """(base_url, api_key, model) for the LLM, read when a client is built.

    BASE_URL and MODEL are required; API_KEY is optional because local
    servers don't check it.
    """
    base_url, model = os.getenv("BASE_URL"), os.getenv("MODEL")
    if base_url and model:
        return base_url, os.getenv("API_KEY"), model
    message = "No LLM backend configured. Set BASE_URL and MODEL (plus API_KEY for hosted endpoints)."
    legacy = [f"{old} -> {new}" for old, new in RENAMED.items() if os.getenv(old)]
    if legacy:
        message += " Renamed settings found: " + "; ".join(legacy) + "."
    raise RuntimeError(message)
