"""Tests for mentions.expand_mentions — @path attachment expansion."""

from make_harness.mentions import expand_mentions


def test_file_mention_attaches_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    expanded, attached = expand_mentions("Explain @a.py please")
    assert attached == ["a.py"]
    assert expanded.startswith("Explain @a.py please")
    assert "[Attached file a.py]" in expanded
    assert "print('hi')" in expanded


def test_folder_mention_attaches_listing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "pkg" / "sub").mkdir()
    expanded, attached = expand_mentions("What's in @pkg ?")
    assert attached == ["pkg"]
    assert "[Attached folder pkg]" in expanded
    assert "mod.py" in expanded
    assert "sub/" in expanded


def test_nonexistent_mentions_stay_plain_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = "email me @gmail.com about @no/such/file.py"
    expanded, attached = expand_mentions(text)
    assert expanded == text
    assert attached == []


def test_trailing_punctuation_is_stripped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    expanded, attached = expand_mentions("Look at @a.py.")
    assert attached == ["a.py"]
    assert "[Attached file a.py]" in expanded


def test_duplicate_mentions_attach_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    expanded, attached = expand_mentions("@a.py and @a.py again")
    assert attached == ["a.py"]
    assert expanded.count("[Attached file a.py]") == 1


def test_nested_path_mention(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "make_harness").mkdir()
    (tmp_path / "make_harness" / "llm.py").write_text("adapter", encoding="utf-8")
    expanded, attached = expand_mentions("How does @make_harness/llm.py work?")
    assert attached == ["make_harness/llm.py"]
    assert "[Attached file make_harness/llm.py]\nadapter" in expanded


def test_huge_file_is_truncated_head_and_tail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "big.txt").write_text("HEAD" + "m" * 50_000 + "TAIL", encoding="utf-8")
    expanded, attached = expand_mentions("summarize @big.txt")
    assert attached == ["big.txt"]
    assert "chars truncated" in expanded
    assert "TAIL" in expanded
    assert len(expanded) < 25_000


def test_no_mentions_is_a_no_op():
    assert expand_mentions("plain question") == ("plain question", [])


def test_empty_folder_mention_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "void").mkdir()
    expanded, attached = expand_mentions("look in @void")
    assert attached == ["void"]
    assert "[Attached folder void]\n(empty)" in expanded


def test_tilde_expands_to_the_home_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    (home / "note.txt").write_text("from home", encoding="utf-8")
    expanded, attached = expand_mentions("read @~/note.txt")
    assert attached == ["~/note.txt"]
    assert "[Attached file ~/note.txt]\nfrom home" in expanded


def test_attachments_are_appended_in_mention_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("A", encoding="utf-8")
    (tmp_path / "b.py").write_text("B", encoding="utf-8")
    expanded, attached = expand_mentions("compare @b.py with @a.py")
    assert attached == ["b.py", "a.py"]
    assert expanded.index("[Attached file b.py]") < expanded.index("[Attached file a.py]")
