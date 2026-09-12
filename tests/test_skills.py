"""Tests for toolsets.skills — SKILL.md discovery, the progressive-
disclosure index, and the load_skill tool."""

import pytest

from make_harness.toolsets import skills


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    """Run inside a temp cwd; skills are discovered under ./skills."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_skill(base, folder, name=None, description="", body="Do the thing."):
    d = base / "skills" / folder
    d.mkdir(parents=True)
    frontmatter = "---\n"
    if name is not None:
        frontmatter += f"name: {name}\n"
    frontmatter += f"description: {description}\n---\n"
    (d / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")


def _write_raw(base, folder, text):
    d = base / "skills" / folder
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")


class TestDiscover:
    def test_no_skills_directory_returns_empty(self, skills_dir):
        assert skills.discover() == {}
        assert skills.skills_index() == ""

    def test_well_formed_skill(self, skills_dir):
        _write_skill(skills_dir, "greeting", name="greeting", description="Say hello nicely.")
        assert skills.discover() == {"greeting": ("Say hello nicely.", "Do the thing.")}

    def test_missing_name_falls_back_to_the_folder_name(self, skills_dir):
        _write_skill(skills_dir, "my-folder", name=None, description="No explicit name.")
        assert set(skills.discover()) == {"my-folder"}

    def test_file_without_frontmatter_is_skipped(self, skills_dir):
        _write_raw(skills_dir, "broken", "Just plain text, no frontmatter.")
        assert skills.discover() == {}

    def test_description_keeps_colons_after_the_first(self, skills_dir):
        _write_skill(skills_dir, "when", name="when", description="Use when: the user says: go")
        assert skills.discover()["when"][0] == "Use when: the user says: go"

    def test_crlf_frontmatter_parses(self, skills_dir):
        d = skills_dir / "skills" / "win"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_bytes(b"---\r\nname: win\r\ndescription: CRLF file.\r\n---\r\nBody line.\r\n")
        assert skills.discover()["win"] == ("CRLF file.", "Body line.")

    def test_extra_frontmatter_fields_are_ignored(self, skills_dir):
        _write_raw(skills_dir, "extra", "---\nname: extra\ndescription: d\nversion: 2\n---\nbody")
        assert skills.discover()["extra"] == ("d", "body")

    def test_bundled_commit_messages_skill_is_discoverable(self):
        # skills/commit-messages/SKILL.md ships with the repo — this guards
        # against its frontmatter silently breaking. No temp cwd: it must be
        # found from the real project root.
        description, body = skills.discover()["commit-messages"]
        assert description
        assert "commit" in body.lower()


def test_skills_index_lists_name_and_description(skills_dir):
    _write_skill(skills_dir, "a", name="alpha", description="First skill.")
    _write_skill(skills_dir, "b", name="beta", description="Second skill.")
    index = skills.skills_index()
    assert "- alpha: First skill." in index
    assert "- beta: Second skill." in index


def test_load_skill_returns_the_body(skills_dir):
    _write_skill(skills_dir, "greeting", name="greeting", description="d", body="Step 1.\nStep 2.")
    assert skills.load_skill("greeting") == "Step 1.\nStep 2."


def test_load_skill_unknown_name_is_a_clean_error():
    assert skills.load_skill("does-not-exist") == "Error: no skill named 'does-not-exist'"
