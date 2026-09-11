"""Tests for toolsets.shell.run_command — exit codes, stderr capture, the
no-output case, and the timeout guard. (Head+tail truncation of long
output is covered in test_truncate.py.)"""

import sys

from make_harness.toolsets import shell


def _py(code):
    return f'"{sys.executable}" -c "{code}"'


def test_reports_a_nonzero_exit_code():
    out = shell.run_command(_py("import sys; sys.exit(3)"))
    assert out.startswith("exit code: 3")


def test_no_output_is_marked_explicitly():
    assert shell.run_command(_py("pass")) == "exit code: 0 (no output)"


def test_stderr_is_captured_alongside_stdout():
    out = shell.run_command(_py("import sys; print('to-stdout'); sys.stderr.write('to-stderr')"))
    assert "to-stdout" in out
    assert "to-stderr" in out


def test_timeout_returns_an_error_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(shell, "TIMEOUT", 1)
    out = shell.run_command(_py("import time; time.sleep(2)"))
    assert out == "Error: command timed out after 1s"
