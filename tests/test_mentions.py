"""Tests for mentions.expand_mentions — @path attachment expansion."""

import pytest

from make_harness.mentions import expand_mentions


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    """Run inside a temp directory so @path resolves against it."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write(base, name, text="x = 1"):
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestFileMentions:
    def test_attaches_content(self, cwd):
        _write(cwd, "a.py", "print('hi')\n")
        expanded, attached = expand_mentions("Explain @a.py please")
        assert attached == ["a.py"]
        assert expanded.startswith("Explain @a.py please")
        assert "[Attached file a.py]" in expanded
        assert "print('hi')" in expanded

    def test_nested_path(self, cwd):
        _write(cwd, "make_harness/llm.py", "adapter")
        expanded, attached = expand_mentions("How does @make_harness/llm.py work?")
        assert attached == ["make_harness/llm.py"]
        assert "[Attached file make_harness/llm.py]\nadapter" in expanded

    def test_trailing_punctuation_is_stripped(self, cwd):
        _write(cwd, "a.py")
        expanded, attached = expand_mentions("Look at @a.py.")
        assert attached == ["a.py"]
        assert "[Attached file a.py]" in expanded

    def test_duplicates_attach_once(self, cwd):
        _write(cwd, "a.py")
        expanded, attached = expand_mentions("@a.py and @a.py again")
        assert attached == ["a.py"]
        assert expanded.count("[Attached file a.py]") == 1

    def test_attachments_follow_mention_order(self, cwd):
        _write(cwd, "a.py", "A")
        _write(cwd, "b.py", "B")
        expanded, attached = expand_mentions("compare @b.py with @a.py")
        assert attached == ["b.py", "a.py"]
        assert expanded.index("[Attached file b.py]") < expanded.index("[Attached file a.py]")

    def test_huge_file_is_truncated_head_and_tail(self, cwd):
        _write(cwd, "big.txt", "HEAD" + "m" * 50_000 + "TAIL")
        expanded, attached = expand_mentions("summarize @big.txt")
        assert attached == ["big.txt"]
        assert "chars truncated" in expanded
        assert "TAIL" in expanded
        assert len(expanded) < 25_000

    def test_tilde_expands_to_the_home_directory(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        _write(home, "note.txt", "from home")
        expanded, attached = expand_mentions("read @~/note.txt")
        assert attached == ["~/note.txt"]
        assert "[Attached file ~/note.txt]\nfrom home" in expanded


class TestFolderMentions:
    def test_attaches_a_listing(self, cwd):
        _write(cwd, "pkg/mod.py")
        (cwd / "pkg" / "sub").mkdir()
        expanded, attached = expand_mentions("What's in @pkg ?")
        assert attached == ["pkg"]
        assert "[Attached folder pkg]" in expanded
        assert "mod.py" in expanded
        assert "sub/" in expanded

    def test_empty_folder_says_so(self, cwd):
        (cwd / "void").mkdir()
        expanded, attached = expand_mentions("look in @void")
        assert attached == ["void"]
        assert "[Attached folder void]\n(empty)" in expanded


@pytest.mark.parametrize(
    "text",
    ["email me @gmail.com about @no/such/file.py", "plain question"],
    ids=["unresolvable-mentions", "no-mentions"],
)
def test_text_without_resolvable_mentions_is_a_no_op(cwd, text):
    assert expand_mentions(text) == (text, [])
