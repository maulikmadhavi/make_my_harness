"""Shared pytest configuration.

make_harness.cli loads a .env file at import time (from the cwd,
~/.make_harness/, or the project root — see cli._load_env_file). The
project root ships one, so any test that imports cli would otherwise pull
the developer's LLM_ENDPOINT / LLM_MODEL / LLM_API_KEY into os.environ for
the rest of the run and make the backend-factory tests depend on who is
running them. MAKE_HARNESS_NO_ENV is the harness's own opt-out switch;
setting it here — before any test module is collected — keeps the whole
suite hermetic. Subprocess tests inherit it too. Tests that exercise the
loader itself lift the switch explicitly (tests/test_cli.py).
"""

import os

os.environ.setdefault("MAKE_HARNESS_NO_ENV", "1")
