"""Tests for the file, shell and truncation toolsets.

fs: read_file (numbered, capped), write_file (creates parents,
overwrites) and str_replace (exact, unique-match edits that keep the
file's line endings). shell: run_command's exit codes, stderr and timeout guard.
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

    @pytest.fixture
    def five_lines(self, tmp_path):
        p = tmp_path / "long.txt"
        p.write_text("\n".join(f"line {i}" for i in range(1, 6)), encoding="utf-8")
        return str(p)

    def test_limit_caps_the_lines_and_says_where_to_continue(self, five_lines):
        out = fs.read_file(five_lines, limit=3)
        assert out.splitlines() == [
            "1\tline 1", "2\tline 2", "3\tline 3", "[not the end of the file: 2 more lines — continue with offset=4]",
        ]

    def test_offset_pages_on_from_there(self, five_lines):
        assert fs.read_file(five_lines, offset=4, limit=3) == "4\tline 4\n5\tline 5"

    def test_offset_past_the_end_says_how_long_the_file_is(self, five_lines):
        assert fs.read_file(five_lines, offset=9) == "[no lines at offset 9: the file has 5 lines]"

    def test_long_lines_stop_at_max_chars_on_a_line_boundary(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fs, "MAX_CHARS", 100)
        p = tmp_path / "wide.txt"
        p.write_text("\n".join("x" * 40 for _ in range(10)), encoding="utf-8")
        out = fs.read_file(str(p)).splitlines()
        assert out[:-1] == [f"{n}\t" + "x" * 40 for n in (1, 2)]
        assert out[-1] == "[not the end of the file: 8 more lines — continue with offset=3]"

    def test_a_single_line_longer_than_max_chars_is_still_returned(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fs, "MAX_CHARS", 10)
        p = tmp_path / "one.txt"
        p.write_text("y" * 50, encoding="utf-8")
        assert fs.read_file(str(p)) == "1\t" + "y" * 50

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


class TestStrReplace:
    @pytest.fixture
    def src(self, tmp_path):
        p = tmp_path / "src.py"
        p.write_bytes(b"def a():\n    return 1\n\ndef b():\n    return 1\n")
        return p

    def test_replaces_a_unique_match(self, src):
        out = fs.str_replace(str(src), "def a():\n    return 1", "def a():\n    return 2")
        assert out == f"Replaced 1 match in {src}"
        assert src.read_bytes() == b"def a():\n    return 2\n\ndef b():\n    return 1\n"

    def test_ambiguous_match_is_refused_and_the_file_is_untouched(self, src):
        before = src.read_bytes()
        out = fs.str_replace(str(src), "return 1", "return 2")
        assert out == (
            f"Error: old_str matches 2 times in {src}. Include surrounding lines "
            "to make it unique, or set allow_multi_edit to replace every match."
        )
        assert src.read_bytes() == before

    def test_allow_multi_edit_replaces_every_match(self, src):
        out = fs.str_replace(str(src), "return 1", "return 2", allow_multi_edit=True)
        assert out == f"Replaced 2 matches in {src}"
        assert src.read_bytes().count(b"return 2") == 2

    def test_missing_text_is_reported(self, src):
        assert fs.str_replace(str(src), "return 3", "x").startswith(f"Error: old_str was not found in {src}")

    def test_empty_old_str_is_refused(self, src):
        # "".count() matches between every character; replacing it would
        # splice new_str all through the file.
        assert fs.str_replace(str(src), "", "x").startswith("Error: old_str is empty")

    def test_lf_file_stays_lf(self, src):
        # On Windows a text-mode write would turn every \n into \r\n.
        fs.str_replace(str(src), "def b", "def c")
        assert b"\r\n" not in src.read_bytes()

    def test_crlf_file_is_matched_and_kept_crlf(self, tmp_path):
        p = tmp_path / "win.txt"
        p.write_bytes(b"one\r\ntwo\r\nthree\r\n")
        # The model copies text from read_file, which shows plain \n endings.
        assert fs.str_replace(str(p), "one\ntwo", "uno\ndos") == f"Replaced 1 match in {p}"
        assert p.read_bytes() == b"uno\r\ndos\r\nthree\r\n"

    def test_round_trips_unicode(self, tmp_path):
        p = tmp_path / "u.txt"
        p.write_bytes("naïve — 日本語\n".encode("utf-8"))
        fs.str_replace(str(p), "日本語", "español")
        assert p.read_bytes().decode("utf-8") == "naïve — español\n"

    def test_schema_makes_allow_multi_edit_an_optional_boolean(self):
        schema = next(s for s in registry.schemas() if s["function"]["name"] == "str_replace")
        params = schema["function"]["parameters"]
        assert params["properties"]["allow_multi_edit"] == {"type": "boolean"}
        assert params["required"] == ["path", "old_str", "new_str"]


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
