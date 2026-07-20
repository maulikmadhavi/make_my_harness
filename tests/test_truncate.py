"""Tests for toolsets.truncate — head+tail capping of tool output.

The old behavior kept only the first N chars, which dropped exactly the
part of shell/build output that matters most: the error at the end.
"""

import sys

from make_harness.toolsets import truncate
from make_harness.toolsets.shell import run_command


def test_under_limit_unchanged():
    assert truncate("short", 100) == "short"


def test_exactly_at_limit_unchanged():
    assert truncate("x" * 100, 100) == "x" * 100


def test_keeps_head_and_tail():
    text = "HEAD" + "m" * 1000 + "TAIL"
    out = truncate(text, 100)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert f"[... {len(text) - 100} chars truncated ...]" in out
    assert len(out) <= 100 + 40  # limit plus the marker line


def test_run_command_keeps_the_tail():
    # A build-log-shaped output: pages of noise, then the error at the end.
    code = "print('A' * 20000); print('THE_ERROR_IS_AT_THE_END')"
    out = run_command(f'"{sys.executable}" -c "{code}"')
    assert out.startswith("exit code: 0")
    assert "THE_ERROR_IS_AT_THE_END" in out
    assert "chars truncated" in out
