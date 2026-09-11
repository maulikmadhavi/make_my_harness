"""Regression test for piped stdin: PowerShell 5.1 prefixes piped input
with a UTF-8 BOM, which must not defeat the REPL's exit check (found
live — 'exit' reached the model as '\\ufeffexit' and it said goodbye)."""

import os
import subprocess
import sys


def test_piped_bom_exit_quits_before_the_llm(tmp_path):
    # A backend must be configured for the REPL to start at all; this one
    # is unreachable on purpose, so any LLM round-trip would surface as an
    # "error:" line instead of silently passing.
    proc = subprocess.run(
        [sys.executable, "-m", "make_harness"],
        input=b"\xef\xbb\xbfexit\r\n",
        capture_output=True,
        cwd=tmp_path,
        timeout=60,
        env={**os.environ, "GROQ_API_KEY": "", "LLM_ENDPOINT": "http://127.0.0.1:9/v1"},
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    assert proc.returncode == 0
    assert "make-harness" in out  # banner printed
    assert "error:" not in out  # exited before any LLM round-trip
