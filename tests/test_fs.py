"""Tests for toolsets.fs — read_file (numbered, capped) and write_file
(creates parents, overwrites), plus the registry's error wrapping for a
missing file."""

from make_harness.tools import registry
from make_harness.toolsets import fs


def test_read_file_numbers_lines_from_one(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("alpha\nbeta\n", encoding="utf-8")
    assert fs.read_file(str(p)) == "1\talpha\n2\tbeta"


def test_read_file_marks_an_empty_file(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    assert fs.read_file(str(p)) == "[empty file]"


def test_read_file_caps_at_max_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "MAX_LINES", 3)
    p = tmp_path / "long.txt"
    p.write_text("\n".join(f"line {i}" for i in range(1, 6)), encoding="utf-8")
    out = fs.read_file(str(p))
    assert out.splitlines()[:3] == ["1\tline 1", "2\tline 2", "3\tline 3"]
    assert out.endswith("[truncated: 2 more lines]")


def test_read_file_replaces_undecodable_bytes(tmp_path):
    p = tmp_path / "bin.txt"
    p.write_bytes(b"ok\xff\xfe\n")
    assert fs.read_file(str(p)).startswith("1\tok")  # no UnicodeDecodeError


def test_missing_file_becomes_a_tool_error_string(tmp_path):
    out = registry.execute("read_file", {"path": str(tmp_path / "nope.txt")})
    assert out.startswith("Error in read_file: FileNotFoundError")


def test_write_file_creates_parents_and_reports_the_size(tmp_path):
    p = tmp_path / "a" / "b" / "c.txt"
    out = fs.write_file(str(p), "hello")
    assert out == f"Wrote 5 chars to {p}"
    assert p.read_text(encoding="utf-8") == "hello"


def test_write_file_overwrites_an_existing_file(tmp_path):
    p = tmp_path / "x.txt"
    fs.write_file(str(p), "first version, longer")
    fs.write_file(str(p), "second")
    assert p.read_text(encoding="utf-8") == "second"


def test_write_then_read_round_trips_unicode(tmp_path):
    p = tmp_path / "u.txt"
    fs.write_file(str(p), "naïve — 日本語")
    assert fs.read_file(str(p)) == "1\tnaïve — 日本語"
