"""Tests for config — the env-file loader and the backend settings.

load_env_file is exercised in-process against a temp directory (the
conftest.py MAKE_HARNESS_NO_ENV switch stops the import-time call from
touching os.environ; the env_sandbox fixture lifts it).
"""

import os

import pytest

from make_harness import config

TEST_KEYS = ("MH_TEST_ALPHA", "MH_TEST_BETA", "MH_TEST_HOME", "MH_TEST_QUOTED")
BACKEND_KEYS = ("BASE_URL", "API_KEY", "MODEL", *config.RENAMED)


@pytest.fixture
def env_sandbox(tmp_path, monkeypatch):
    """chdir into a temp dir, point ~ at a temp home, lift the NO_ENV
    switch, and restore os.environ wholesale afterwards — the loader
    writes to os.environ directly, so monkeypatch alone can't undo keys
    it creates."""
    saved = dict(os.environ)
    home = tmp_path / "home"
    (home / ".agents").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("MAKE_HARNESS_NO_ENV", raising=False)
    for key in TEST_KEYS:
        os.environ.pop(key, None)
    yield tmp_path, home
    os.environ.clear()
    os.environ.update(saved)


def _write_env(path, text):
    path.write_text(text, encoding="utf-8")


class TestLoadEnvFile:
    def test_loads_keys_from_the_cwd_env_file(self, env_sandbox):
        tmp_path, _ = env_sandbox
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=one\n")
        config.load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "one"

    def test_skips_comments_and_blank_lines_and_strips_quotes(self, env_sandbox):
        tmp_path, _ = env_sandbox
        _write_env(
            tmp_path / ".env",
            "# a comment\n\nMH_TEST_QUOTED=\"quoted value\"\nMH_TEST_BETA = 'x=y' \n",
        )
        config.load_env_file()
        assert os.environ["MH_TEST_QUOTED"] == "quoted value"
        assert os.environ["MH_TEST_BETA"] == "x=y"  # split on the first '=' only

    def test_does_not_override_a_variable_already_in_the_environment(self, env_sandbox, monkeypatch):
        tmp_path, _ = env_sandbox
        monkeypatch.setenv("MH_TEST_ALPHA", "from-shell")
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=from-file\n")
        config.load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "from-shell"

    def test_make_harness_no_env_disables_loading(self, env_sandbox, monkeypatch):
        tmp_path, _ = env_sandbox
        monkeypatch.setenv("MAKE_HARNESS_NO_ENV", "1")
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=one\n")
        config.load_env_file()
        assert "MH_TEST_ALPHA" not in os.environ

    def test_falls_back_to_the_home_agents_env_file(self, env_sandbox):
        _, home = env_sandbox
        _write_env(home / ".agents" / "env", "MH_TEST_HOME=from-home\n")
        config.load_env_file()
        assert os.environ["MH_TEST_HOME"] == "from-home"

    def test_stops_after_the_first_file_found(self, env_sandbox):
        tmp_path, home = env_sandbox
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=cwd\n")
        _write_env(home / ".agents" / "env", "MH_TEST_ALPHA=home\nMH_TEST_HOME=home\n")
        config.load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "cwd"
        assert "MH_TEST_HOME" not in os.environ  # the second file was never read

    def test_reads_a_utf8_bom_file_without_mangling_the_first_key(self, env_sandbox):
        tmp_path, _ = env_sandbox
        # Notepad and PowerShell's Set-Content both write UTF-8 with a BOM. Read
        # under the locale encoding the BOM became part of the first key's name,
        # so the setting silently vanished.
        (tmp_path / ".env").write_bytes("﻿MH_TEST_ALPHA=one\n".encode("utf-8"))
        config.load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "one"

    def test_an_undecodable_file_is_skipped_rather_than_crashing(self, env_sandbox):
        tmp_path, home = env_sandbox
        # UTF-16 raises UnicodeDecodeError, which is a ValueError — not an OSError,
        # so it used to escape the loader and crash at import time.
        (tmp_path / ".env").write_bytes("MH_TEST_ALPHA=utf16\n".encode("utf-16"))
        _write_env(home / ".agents" / "env", "MH_TEST_HOME=from-home\n")
        config.load_env_file()
        assert os.environ["MH_TEST_HOME"] == "from-home"
        assert "MH_TEST_ALPHA" not in os.environ


@pytest.fixture
def clean_backend(monkeypatch):
    for key in BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestBackend:
    def test_reads_base_url_api_key_and_model(self, clean_backend, monkeypatch):
        monkeypatch.setenv("BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("MODEL", "qwen")
        monkeypatch.setenv("API_KEY", "sk-x")
        assert config.backend() == ("http://localhost:11434/v1", "sk-x", "qwen")

    def test_api_key_is_optional(self, clean_backend, monkeypatch):
        monkeypatch.setenv("BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("MODEL", "qwen")
        assert config.backend() == ("http://localhost:11434/v1", None, "qwen")

    @pytest.mark.parametrize("present", ["BASE_URL", "MODEL", None], ids=["no-model", "no-base-url", "neither"])
    def test_base_url_and_model_are_both_required(self, clean_backend, monkeypatch, present):
        if present:
            monkeypatch.setenv(present, "x")
        with pytest.raises(RuntimeError, match="Set BASE_URL and MODEL") as exc:
            config.backend()
        assert "Renamed" not in str(exc.value)

    def test_names_the_rename_for_settings_from_before_the_sdk(self, clean_backend, monkeypatch):
        monkeypatch.setenv("LLM_ENDPOINT", "http://localhost:11434/v1")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
        with pytest.raises(RuntimeError) as exc:
            config.backend()
        assert "LLM_ENDPOINT -> BASE_URL" in str(exc.value)
        assert "GROQ_API_KEY -> API_KEY (with BASE_URL=https://api.groq.com/openai/v1)" in str(exc.value)
