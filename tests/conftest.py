"""Shared pytest configuration.

make_harness.config loads a .env file at import time (from the cwd or
~/.agents/env — see config.load_env_file). A developer checkout usually has
one, so any test that imports config would otherwise pull the developer's
BASE_URL / MODEL / API_KEY into os.environ for the rest of the run and make
the backend tests depend on who is running them. MAKE_HARNESS_NO_ENV is the
harness's own opt-out switch; setting it here — before any test module is
collected — keeps the whole suite hermetic. Subprocess tests inherit it too. Tests that exercise the
loader itself lift the switch explicitly (tests/test_config.py).
"""

import os

import pytest

os.environ.setdefault("MAKE_HARNESS_NO_ENV", "1")


@pytest.fixture(autouse=True)
def _sweep_spilled_output():
    """Delete any temp files history.cap wrote during a test, the way the
    REPL does when a turn ends."""
    yield
    from make_harness import history

    history.sweep()
