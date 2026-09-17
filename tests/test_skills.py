"""Tests for toolsets.skills — SKILL.md discovery in ./.agents/skills and
~/.agents/skills, the progressive-disclosure index, and the load_skill tool."""

import pytest

from make_harness.toolsets import skills


@pytest.fixture
def skills_dir(tmp_path, monkeypatch):
    """Run inside a temp cwd with an empty temp home; returns the project's
    ./.agents/skills directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project / ".agents" / "skills"


@pytest.fixture
def home_skills_dir(skills_dir, tmp_path):
    return tmp_path / "home" / ".agents" / "skills"


def _write_skill(base, folder, name=None, description="", body="Do the thing."):
    d = base / folder
    d.mkdir(parents=True)
    frontmatter = "---\n"
    if name is not None:
        frontmatter += f"name: {name}\n"
    frontmatter += f"description: {description}\n---\n"
    (d / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")


def _write_raw(base, folder, text):
    d = base / folder
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
        d = skills_dir / "win"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_bytes(b"---\r\nname: win\r\ndescription: CRLF file.\r\n---\r\nBody line.\r\n")
        assert skills.discover()["win"] == ("CRLF file.", "Body line.")

    def test_multi_line_yaml_description_is_folded_to_one_line(self, skills_dir):
        _write_raw(skills_dir, "long", "---\nname: long\ndescription: >\n  Spans two\n  lines.\n---\nbody")
        assert skills.discover()["long"] == ("Spans two lines.", "body")

    def test_quoted_yaml_values_are_unquoted(self, skills_dir):
        _write_raw(skills_dir, "q", '---\nname: "q"\ndescription: "Has: a colon"\n---\nbody')
        assert skills.discover()["q"] == ("Has: a colon", "body")

    def test_home_skills_are_discovered(self, home_skills_dir):
        _write_skill(home_skills_dir, "mine", name="mine", description="Personal skill.")
        assert skills.discover() == {"mine": ("Personal skill.", "Do the thing.")}

    def test_project_skill_wins_a_name_clash_with_home(self, skills_dir, home_skills_dir):
        _write_skill(skills_dir, "shared", name="shared", description="project", body="P")
        _write_skill(home_skills_dir, "shared", name="shared", description="home", body="H")
        assert skills.discover()["shared"] == ("project", "P")

    def test_extra_frontmatter_fields_are_ignored(self, skills_dir):
        _write_raw(skills_dir, "extra", "---\nname: extra\ndescription: d\nversion: 2\n---\nbody")
        assert skills.discover()["extra"] == ("d", "body")

    def test_bundled_commit_messages_skill_is_discoverable(self):
        # .agents/skills/commit-messages/SKILL.md ships with the repo — this guards
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
