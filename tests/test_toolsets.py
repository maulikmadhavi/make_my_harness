"""Tests for the file, shell and truncation toolsets.

fs: read_file (numbered, capped) and write_file (creates parents,
overwrites). shell: run_command's exit codes, stderr and timeout guard.
truncate: head+tail capping — the old behavior kept only the first N
chars, dropping exactly the part of build output that matters most, the
error at the end.
"""

import sys

import pytest

from make_harness.tools import registry
from make_harness.toolsets import fs, truncate
from make_harness.toolsets.shell import run_command


class TestReadFile:
    def test_numbers_lines_from_one(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_text("alpha\nbeta\n", encoding="utf-8")
        assert fs.read_file(str(p)) == "1\talpha\n2\tbeta"

    def test_marks_an_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        assert fs.read_file(str(p)) == "[empty file]"

    def test_caps_at_max_lines(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fs, "MAX_LINES", 3)
        p = tmp_path / "long.txt"
        p.write_text("\n".join(f"line {i}" for i in range(1, 6)), encoding="utf-8")
        out = fs.read_file(str(p))
        assert out.splitlines()[:3] == ["1\tline 1", "2\tline 2", "3\tline 3"]
        assert out.endswith("[truncated: 2 more lines]")

    def test_replaces_undecodable_bytes(self, tmp_path):
        p = tmp_path / "bin.txt"
        p.write_bytes(b"ok\xff\xfe\n")
        assert fs.read_file(str(p)).startswith("1\tok")  # no UnicodeDecodeError

    def test_missing_file_becomes_a_tool_error_string(self, tmp_path):
        out = registry.execute("read_file", {"path": str(tmp_path / "nope.txt")})
        assert out.startswith("Error in read_file: FileNotFoundError")


class TestWriteFile:
    def test_creates_parents_and_reports_the_size(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.txt"
        assert fs.write_file(str(p), "hello") == f"Wrote 5 chars to {p}"
        assert p.read_text(encoding="utf-8") == "hello"

    def test_overwrites_an_existing_file(self, tmp_path):
        p = tmp_path / "x.txt"
        fs.write_file(str(p), "first version, longer")
        fs.write_file(str(p), "second")
        assert p.read_text(encoding="utf-8") == "second"

    def test_round_trips_unicode(self, tmp_path):
        p = tmp_path / "u.txt"
        fs.write_file(str(p), "naïve — 日本語")
        assert fs.read_file(str(p)) == "1\tnaïve — 日本語"


def _py(code):
    return f'"{sys.executable}" -c "{code}"'


class TestRunCommand:
    def test_reports_a_nonzero_exit_code(self):
        assert run_command(_py("import sys; sys.exit(3)")).startswith("exit code: 3")

    def test_no_output_is_marked_explicitly(self):
        assert run_command(_py("pass")) == "exit code: 0 (no output)"

    def test_stderr_is_captured_alongside_stdout(self):
        out = run_command(_py("import sys; print('to-stdout'); sys.stderr.write('to-stderr')"))
        assert "to-stdout" in out
        assert "to-stderr" in out

    def test_timeout_returns_an_error_instead_of_hanging(self, monkeypatch):
        from make_harness.toolsets import shell

        monkeypatch.setattr(shell, "TIMEOUT", 1)
        assert shell.run_command(_py("import time; time.sleep(2)")) == "Error: command timed out after 1s"

    def test_long_output_keeps_the_tail(self):
        # A build-log-shaped output: pages of noise, then the error at the end.
        out = run_command(_py("print('A' * 20000); print('THE_ERROR_IS_AT_THE_END')"))
        assert out.startswith("exit code: 0")
        assert "THE_ERROR_IS_AT_THE_END" in out
        assert "chars truncated" in out


class TestTruncate:
    @pytest.mark.parametrize("text", ["short", "x" * 100], ids=["under-limit", "exactly-at-limit"])
    def test_within_the_limit_is_unchanged(self, text):
        assert truncate(text, 100) == text

    def test_keeps_head_and_tail(self):
        text = "HEAD" + "m" * 1000 + "TAIL"
        out = truncate(text, 100)
        assert out.startswith("HEAD")
        assert out.endswith("TAIL")
        assert f"[... {len(text) - 100} chars truncated ...]" in out
        assert len(out) <= 100 + 40  # limit plus the marker line
