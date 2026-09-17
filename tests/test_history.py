"""Tests for history — cap (trim + spill to a temp file), sweep, strip,
fit, and the frozen prefix none of them may touch."""

from pathlib import Path

import pytest

from make_harness import history
from make_harness.history import CAP, STUB, SUMMARY, TRIMMED


def _call(call_id, name="read_file"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}},
    ]}


def _result(call_id, content):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _spilled_path(capped):
    return Path(capped.split("saved to ", 1)[1].split(" — ", 1)[0])


class TestCap:
    def test_short_output_is_unchanged_and_nothing_is_saved(self):
        assert history.cap("short") == "short"
        assert history._spills == []

    def test_long_output_keeps_head_and_tail_and_spills_the_whole(self):
        text = "HEAD" + "m" * (CAP * 2) + "TAIL"
        capped = history.cap(text)
        assert capped.startswith("HEAD")
        assert "TAIL" in capped
        assert len(capped) < CAP + 400
        path = _spilled_path(capped)
        assert path.read_text(encoding="utf-8") == text
        assert "read_file offset/limit" in capped

    def test_sweep_deletes_this_turns_files(self):
        path = _spilled_path(history.cap("x" * (CAP + 1)))
        assert path.exists()
        history.sweep()
        assert not path.exists()
        assert history._spills == []

    def test_unwritable_temp_dir_still_trims(self, monkeypatch):
        def fail(text):
            raise OSError("read-only")

        monkeypatch.setattr(history, "_spill", fail)
        capped = history.cap("x" * (CAP + 1))
        assert capped.endswith("[the full output could not be saved]")


class TestStrip:
    def test_shrinks_long_tool_results_only(self):
        messages = [
            {"role": "system", "content": "s" * 1000},
            {"role": "user", "content": "u" * 1000},
            _call("c1"),
            _result("c1", "r" * 1000),
            _result("c2", "short"),
        ]
        assert history.strip(messages) == 1
        assert messages[0]["content"] == "s" * 1000
        assert messages[1]["content"] == "u" * 1000
        assert messages[3]["content"].startswith("r" * STUB + f"\n{TRIMMED} 700 more chars")
        assert messages[4]["content"] == "short"

    def test_stripping_twice_is_a_no_op(self):
        messages = [_call("c1"), _result("c1", "r" * 1000)]
        history.strip(messages)
        once = messages[1]["content"]
        assert history.strip(messages) == 0
        assert messages[1]["content"] == once

    def test_never_touches_the_frozen_prefix(self):
        messages = [
            {"role": "system", "content": "s"},
            _call("c1"),
            _result("c1", "old" * 500),
            {"role": "user", "content": SUMMARY + "\nnote\n</summary>"},
            _call("c2"),
            _result("c2", "new" * 500),
        ]
        assert history.locked(messages) == 4
        assert history.strip(messages) == 1
        assert messages[2]["content"] == "old" * 500
        assert TRIMMED in messages[5]["content"]

    def test_a_user_quoting_the_summary_tag_mid_message_does_not_lock(self):
        messages = [{"role": "user", "content": f"what does {SUMMARY} mean?"}]
        assert history.locked(messages) == 0


class TestFit:
    def test_under_budget_drops_nothing(self):
        messages = [_call("c1"), _result("c1", "x" * 400)]
        assert history.fit(messages, budget=10_000) == 0
        assert messages[1]["content"] == "x" * 400

    def test_drops_oldest_tool_results_until_it_fits(self):
        messages = [
            {"role": "user", "content": "go"},
            _call("c1"), _result("c1", "a" * 4000),
            _call("c2"), _result("c2", "b" * 4000),
            _call("c3"), _result("c3", "c" * 4000),
        ]
        dropped = history.fit(messages, budget=history.estimate(messages) - 1500)
        assert dropped == 2
        assert messages[2]["content"] == f"{TRIMMED} dropped to fit the context window.]"
        assert messages[4]["content"] == f"{TRIMMED} dropped to fit the context window.]"
        assert messages[6]["content"] == "c" * 4000  # the newest survives

    def test_defaults_to_the_compaction_threshold(self, monkeypatch):
        from make_harness import config

        monkeypatch.setattr(config, "CONTEXT_WINDOW", 1000)
        messages = [_call("c1"), _result("c1", "x" * 8000)]
        assert history.fit(messages) == 1

    @pytest.mark.parametrize("role", ["user", "assistant", "system"])
    def test_never_drops_non_tool_messages(self, role):
        messages = [{"role": role, "content": "x" * 8000}]
        assert history.fit(messages, budget=1) == 0
