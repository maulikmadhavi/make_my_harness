"""Tests for log.RunLog — one JSONL file per session, one event per line."""

import json
import re
from pathlib import Path

from make_harness.log import RunLog


def test_creates_the_log_dir_and_a_timestamped_filename(tmp_path):
    log = RunLog(log_dir=tmp_path / "logs")
    assert (tmp_path / "logs").is_dir()
    assert re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{8}\.jsonl", log.path.name)
    assert log.path.name.endswith(f"_{log.run_id}.jsonl")


def test_the_file_appears_on_the_first_event(tmp_path):
    log = RunLog(log_dir=tmp_path)
    assert not log.path.exists()
    log.event("boot")
    assert log.path.exists()


def test_each_event_is_one_json_line_with_the_common_fields(tmp_path):
    log = RunLog(log_dir=tmp_path)
    log.event("first", step=0, tool="read_file")
    log.event("second", answer="done")
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert (first["kind"], first["step"], first["tool"]) == ("first", 0, "read_file")
    assert (second["kind"], second["answer"]) == ("second", "done")
    for record in (first, second):
        assert record["run"] == log.run_id
        assert isinstance(record["ts"], float)


def test_non_json_values_are_coerced_with_str(tmp_path):
    log = RunLog(log_dir=tmp_path)
    log.event("mention", attachment=Path("a") / "b.py")
    record = json.loads(log.path.read_text(encoding="utf-8"))
    assert record["attachment"] == str(Path("a") / "b.py")


def test_unicode_is_written_verbatim_not_escaped(tmp_path):
    log = RunLog(log_dir=tmp_path)
    log.event("user_message", content="héllo — 世界")
    raw = log.path.read_text(encoding="utf-8")
    assert "héllo — 世界" in raw
    assert "\\u" not in raw


def test_two_sessions_get_distinct_run_ids_and_files(tmp_path):
    a, b = RunLog(log_dir=tmp_path), RunLog(log_dir=tmp_path)
    assert a.run_id != b.run_id
    assert a.path != b.path
