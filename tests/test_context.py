"""Tests for context — the per-request <env> block, how it is attached to
a request, and ChangeTracker against a real temporary git repository."""

import subprocess

import pytest

from make_harness import context


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repository on branch `trunk` with one committed file, as the cwd."""
    _git(tmp_path, "init", "-q", "-b", "trunk")
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestReminder:
    def test_env_block_has_date_and_branch(self):
        block = context.reminder("trunk")
        assert block.startswith("<env>\ndate: ")
        assert block.endswith("git branch: trunk\n</env>")
        assert "<system-reminder>" not in block

    def test_changed_files_are_listed_in_a_system_reminder(self):
        block = context.reminder("trunk", {"a.py": "modified", "b.py": "new"})
        assert block.endswith(
            "<system-reminder>\n"
            "These files changed since your last turn. Read them again before editing:\n"
            "modified: a.py\nnew: b.py\n</system-reminder>"
        )


class TestWithReminder:
    def test_merged_into_a_trailing_user_message(self):
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
        sent = context.with_reminder(messages, "<env></env>")
        assert sent == [messages[0], {"role": "user", "content": "hi\n\n<env></env>"}]
        assert messages[1] == {"role": "user", "content": "hi"}  # the transcript is untouched

    def test_appended_after_tool_results(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": []},
            {"role": "tool", "tool_call_id": "c1", "content": "r"},
        ]
        sent = context.with_reminder(messages, "<env></env>")
        assert sent[:3] == messages
        assert sent[3] == {"role": "user", "content": "<env></env>"}
        assert len(messages) == 3


class TestGit:
    def test_branch_in_a_repository(self, repo):
        assert context.branch() == "trunk"

    def test_branch_outside_a_repository(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
        assert context.branch() == "(not a git repository)"
        assert context.git_state() == {}


class TestChangeTracker:
    def test_nothing_is_reported_before_the_first_snapshot(self, repo):
        (repo / "a.py").write_text("two\n", encoding="utf-8")
        assert context.ChangeTracker().changes() == {}

    def test_reports_edits_made_after_the_snapshot(self, repo):
        tracker = context.ChangeTracker()
        tracker.snapshot()
        (repo / "a.py").write_text("two\n", encoding="utf-8")
        (repo / "b.py").write_text("new\n", encoding="utf-8")
        assert tracker.changes() == {"a.py": "modified", "b.py": "new"}

    def test_an_already_dirty_file_edited_again_is_reported(self, repo):
        (repo / "a.py").write_text("two\n", encoding="utf-8")
        tracker = context.ChangeTracker()
        tracker.snapshot()
        assert tracker.changes() == {}
        (repo / "a.py").write_text("three, and longer\n", encoding="utf-8")
        assert tracker.changes() == {"a.py": "modified"}

    def test_a_reverted_file_is_reported(self, repo):
        (repo / "a.py").write_text("two\n", encoding="utf-8")
        tracker = context.ChangeTracker()
        tracker.snapshot()
        _git(repo, "checkout", "-q", "--", "a.py")
        assert tracker.changes() == {"a.py": "committed or reverted"}

    def test_paths_are_repository_relative_from_a_subdirectory(self, repo, monkeypatch):
        (repo / "pkg").mkdir()
        (repo / "pkg" / "m.py").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "pkg/m.py")
        _git(repo, "commit", "-q", "-m", "pkg")
        monkeypatch.chdir(repo / "pkg")
        tracker = context.ChangeTracker()
        tracker.snapshot()
        (repo / "pkg" / "m.py").write_text("y, longer\n", encoding="utf-8")
        assert tracker.changes() == {"pkg/m.py": "modified"}
