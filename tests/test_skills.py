"""Tests for toolsets.skills — SKILL.md discovery, the progressive-
disclosure index, and the load_skill tool."""

from make_harness.toolsets import skills


def _write_skill(base, folder, name=None, description="", body="Do the thing."):
    d = base / "skills" / folder
    d.mkdir(parents=True)
    frontmatter = "---\n"
    if name is not None:
        frontmatter += f"name: {name}\n"
    frontmatter += f"description: {description}\n---\n"
    (d / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")


def test_no_skills_directory_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert skills.discover() == {}
    assert skills.skills_index() == ""


def test_discovers_a_well_formed_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "greeting", name="greeting", description="Say hello nicely.")
    found = skills.discover()
    assert set(found) == {"greeting"}
    description, body = found["greeting"]
    assert description == "Say hello nicely."
    assert body == "Do the thing."


def test_missing_name_field_falls_back_to_folder_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "my-folder", name=None, description="No explicit name.")
    assert set(skills.discover()) == {"my-folder"}


def test_file_without_frontmatter_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "skills" / "broken"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("Just plain text, no frontmatter.", encoding="utf-8")
    assert skills.discover() == {}


def test_skills_index_lists_name_and_description(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "a", name="alpha", description="First skill.")
    _write_skill(tmp_path, "b", name="beta", description="Second skill.")
    index = skills.skills_index()
    assert "- alpha: First skill." in index
    assert "- beta: Second skill." in index


def test_load_skill_returns_the_body(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(tmp_path, "greeting", name="greeting", description="d", body="Step 1.\nStep 2.")
    assert skills.load_skill("greeting") == "Step 1.\nStep 2."


def test_load_skill_unknown_name_is_a_clean_error():
    assert skills.load_skill("does-not-exist") == "Error: no skill named 'does-not-exist'"


def test_bundled_commit_messages_skill_is_discoverable():
    # skills/commit-messages/SKILL.md ships with the repo — this guards
    # against its frontmatter silently breaking.
    found = skills.discover()
    assert "commit-messages" in found
    description, body = found["commit-messages"]
    assert description
    assert "commit" in body.lower()
