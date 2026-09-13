"""Tests for cli — the .env loader, startup wiring, and the argparse
entry point.

_load_env_file is exercised in-process against a temp directory (the
conftest.py MAKE_HARNESS_NO_ENV switch stops the import-time call from
touching os.environ; the env_sandbox fixture lifts it). The CLI flags and
the piped-stdin REPL are driven end to end in a subprocess.
"""

import os
import platform
import subprocess
import sys

import pytest

from make_harness import __version__, cli
from make_harness.tools import registry

TEST_KEYS = ("MH_TEST_ALPHA", "MH_TEST_BETA", "MH_TEST_HOME", "MH_TEST_QUOTED")
BACKEND_KEYS = ("GROQ_API_KEY", "LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY")


@pytest.fixture
def env_sandbox(tmp_path, monkeypatch):
    """chdir into a temp dir, point ~ at a temp home, lift the NO_ENV
    switch, and restore os.environ wholesale afterwards — the loader
    writes to os.environ directly, so monkeypatch alone can't undo keys
    it creates."""
    saved = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir()
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
        cli._load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "one"

    def test_skips_comments_and_blank_lines_and_strips_quotes(self, env_sandbox):
        tmp_path, _ = env_sandbox
        _write_env(
            tmp_path / ".env",
            "# a comment\n\nMH_TEST_QUOTED=\"quoted value\"\nMH_TEST_BETA = 'x=y' \n",
        )
        cli._load_env_file()
        assert os.environ["MH_TEST_QUOTED"] == "quoted value"
        assert os.environ["MH_TEST_BETA"] == "x=y"  # split on the first '=' only

    def test_does_not_override_a_variable_already_in_the_environment(self, env_sandbox, monkeypatch):
        tmp_path, _ = env_sandbox
        monkeypatch.setenv("MH_TEST_ALPHA", "from-shell")
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=from-file\n")
        cli._load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "from-shell"

    def test_make_harness_no_env_disables_loading(self, env_sandbox, monkeypatch):
        tmp_path, _ = env_sandbox
        monkeypatch.setenv("MAKE_HARNESS_NO_ENV", "1")
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=one\n")
        cli._load_env_file()
        assert "MH_TEST_ALPHA" not in os.environ

    def test_falls_back_to_the_home_dot_make_harness_file(self, env_sandbox):
        _, home = env_sandbox
        (home / ".make_harness").mkdir()
        _write_env(home / ".make_harness" / ".env", "MH_TEST_HOME=from-home\n")
        cli._load_env_file()
        assert os.environ["MH_TEST_HOME"] == "from-home"

    def test_stops_after_the_first_file_found(self, env_sandbox):
        tmp_path, home = env_sandbox
        _write_env(tmp_path / ".env", "MH_TEST_ALPHA=cwd\n")
        (home / ".make_harness").mkdir()
        _write_env(home / ".make_harness" / ".env", "MH_TEST_ALPHA=home\nMH_TEST_HOME=home\n")
        cli._load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "cwd"
        assert "MH_TEST_HOME" not in os.environ  # the second file was never read

    def test_reads_a_utf8_bom_file_without_mangling_the_first_key(self, env_sandbox):
        tmp_path, _ = env_sandbox
        # Notepad and PowerShell's Set-Content both write UTF-8 with a BOM. Read
        # under the locale encoding the BOM became part of the first key's name,
        # so the setting silently vanished.
        (tmp_path / ".env").write_bytes("﻿MH_TEST_ALPHA=one\n".encode("utf-8"))
        cli._load_env_file()
        assert os.environ["MH_TEST_ALPHA"] == "one"

    def test_an_undecodable_file_is_skipped_rather_than_crashing(self, env_sandbox):
        tmp_path, home = env_sandbox
        # UTF-16 raises UnicodeDecodeError, which is a ValueError — not an OSError,
        # so it used to escape the loader and crash at import time.
        (tmp_path / ".env").write_bytes("MH_TEST_ALPHA=utf16\n".encode("utf-16"))
        (home / ".make_harness").mkdir()
        _write_env(home / ".make_harness" / ".env", "MH_TEST_HOME=from-home\n")
        cli._load_env_file()
        assert os.environ["MH_TEST_HOME"] == "from-home"
        assert "MH_TEST_ALPHA" not in os.environ


class TestStartupWiring:
    def test_registers_the_documented_toolset(self):
        names = {t["function"]["name"] for t in registry.schemas()}
        assert {
            "read_file", "write_file", "run_command", "load_skill",
            "web_search", "http_request", "save_memory", "read_memory",
        } <= names

    def test_system_prompt_names_the_platform_and_cwd(self):
        assert platform.system() in cli.SYSTEM_PROMPT
        assert os.getcwd() in cli.SYSTEM_PROMPT


def _run_cli(*args, cwd, stdin=b"", **env_overrides):
    """Run `python -m make_harness` with the developer's backend config
    stripped out, so the subprocess never reaches a real LLM."""
    env = {k: v for k, v in os.environ.items() if k not in BACKEND_KEYS}
    env["MAKE_HARNESS_NO_ENV"] = "1"
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "make_harness", *args],
        input=stdin, capture_output=True, cwd=cwd, timeout=60, env=env,
    )


class TestEntryPoint:
    @pytest.mark.parametrize(
        "flag,expected", [("--version", f"make-harness {__version__}"), ("--help", "make-harness")],
    )
    def test_flag_exits_zero_and_prints(self, tmp_path, flag, expected):
        proc = _run_cli(flag, cwd=tmp_path)
        assert proc.returncode == 0
        assert expected in proc.stdout.decode()

    def test_piped_bom_exit_quits_before_the_llm(self, tmp_path):
        # PowerShell 5.1 prefixes piped input with a UTF-8 BOM, which must not
        # defeat the REPL's exit check (found live — 'exit' reached the model
        # as '﻿exit' and it said goodbye). The endpoint below is
        # unreachable on purpose, so any round-trip would surface as "error:".
        proc = _run_cli(
            cwd=tmp_path, stdin=b"\xef\xbb\xbfexit\r\n", LLM_ENDPOINT="http://127.0.0.1:9/v1",
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        assert "make-harness" in out  # banner printed
        assert "error:" not in out  # exited before any LLM round-trip

    def test_piped_slash_exit_stops_before_later_input(self, tmp_path):
        # End of input would stop the REPL on its own, so a bare "/exit"
        # could not show it worked; the "hello" after it would reach the
        # unreachable endpoint and print "error:" if the session carried on.
        proc = _run_cli(
            cwd=tmp_path, stdin=b"/exit\nhello\n", LLM_ENDPOINT="http://127.0.0.1:9/v1",
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        assert "Goodbye." in out
        assert "error:" not in out
