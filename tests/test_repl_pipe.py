"""Regression test for piped stdin: PowerShell 5.1 prefixes piped input
with a UTF-8 BOM, which must not defeat the REPL's exit check (found
live — 'exit' reached the model as '\\ufeffexit' and it said goodbye)."""

import os
import subprocess
import sys


def test_piped_bom_exit_quits_before_the_llm(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "make_harness"],
        input=b"\xef\xbb\xbfexit\r\n",
        capture_output=True,
        cwd=tmp_path,
        timeout=60,
        env={**os.environ, "GROQ_API_KEY": ""},
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    assert proc.returncode == 0
    assert "make-harness" in out  # banner printed
    assert "agent >" not in out  # exited before any LLM round-trip
