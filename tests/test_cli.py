"""Tests for cli — the .env loader and the argparse entry point.

_load_env_file is exercised in-process against a temp directory (the
conftest.py MAKE_HARNESS_NO_ENV switch stops the import-time call from
touching os.environ; each test here lifts it explicitly). The CLI flags
are exercised end to end in a subprocess, the same way test_repl_pipe.py
drives the REPL.
"""

import os
import platform
import subprocess
import sys

import pytest

from make_harness import __version__, cli
from make_harness.tools import registry

TEST_KEYS = ("MH_TEST_ALPHA", "MH_TEST_BETA", "MH_TEST_HOME", "MH_TEST_QUOTED")


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


# --- _load_env_file --------------------------------------------------------

def test_loads_keys_from_the_cwd_env_file(env_sandbox):
    tmp_path, _ = env_sandbox
    _write_env(tmp_path / ".env", "MH_TEST_ALPHA=one\n")
    cli._load_env_file()
    assert os.environ["MH_TEST_ALPHA"] == "one"


def test_skips_comments_and_blank_lines_and_strips_quotes(env_sandbox):
    tmp_path, _ = env_sandbox
    _write_env(
        tmp_path / ".env",
        "# a comment\n\nMH_TEST_QUOTED=\"quoted value\"\nMH_TEST_BETA = 'x=y' \n",
    )
    cli._load_env_file()
    assert os.environ["MH_TEST_QUOTED"] == "quoted value"
    assert os.environ["MH_TEST_BETA"] == "x=y"  # split on the first '=' only


def test_does_not_override_a_variable_already_in_the_environment(env_sandbox, monkeypatch):
    tmp_path, _ = env_sandbox
    monkeypatch.setenv("MH_TEST_ALPHA", "from-shell")
    _write_env(tmp_path / ".env", "MH_TEST_ALPHA=from-file\n")
    cli._load_env_file()
    assert os.environ["MH_TEST_ALPHA"] == "from-shell"


def test_make_harness_no_env_disables_loading(env_sandbox, monkeypatch):
    tmp_path, _ = env_sandbox
    monkeypatch.setenv("MAKE_HARNESS_NO_ENV", "1")
    _write_env(tmp_path / ".env", "MH_TEST_ALPHA=one\n")
    cli._load_env_file()
    assert "MH_TEST_ALPHA" not in os.environ


def test_falls_back_to_the_home_dot_make_harness_file(env_sandbox):
    _, home = env_sandbox
    (home / ".make_harness").mkdir()
    _write_env(home / ".make_harness" / ".env", "MH_TEST_HOME=from-home\n")
    cli._load_env_file()
    assert os.environ["MH_TEST_HOME"] == "from-home"


def test_stops_after_the_first_file_found(env_sandbox):
    tmp_path, home = env_sandbox
    _write_env(tmp_path / ".env", "MH_TEST_ALPHA=cwd\n")
    (home / ".make_harness").mkdir()
    _write_env(home / ".make_harness" / ".env", "MH_TEST_ALPHA=home\nMH_TEST_HOME=home\n")
    cli._load_env_file()
    assert os.environ["MH_TEST_ALPHA"] == "cwd"
    assert "MH_TEST_HOME" not in os.environ  # the second file was never read


# --- startup wiring --------------------------------------------------------

def test_cli_registers_the_documented_toolset():
    names = {t["function"]["name"] for t in registry.schemas()}
    assert {
        "read_file", "write_file", "run_command", "load_skill",
        "web_search", "http_request", "save_memory", "read_memory",
    } <= names


def test_system_prompt_names_the_platform_and_cwd():
    assert platform.system() in cli.SYSTEM_PROMPT
    assert os.getcwd() in cli.SYSTEM_PROMPT


# --- argparse entry point, end to end --------------------------------------

def _run_cli(*args, cwd):
    env = {k: v for k, v in os.environ.items()
           if k not in {"GROQ_API_KEY", "LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY"}}
    env["MAKE_HARNESS_NO_ENV"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "make_harness", *args],
        input=b"", capture_output=True, cwd=cwd, timeout=60, env=env,
    )


def test_version_flag(tmp_path):
    proc = _run_cli("--version", cwd=tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == f"make-harness {__version__}"


def test_help_flag(tmp_path):
    proc = _run_cli("--help", cwd=tmp_path)
    assert proc.returncode == 0
    assert "make-harness" in proc.stdout.decode()


# --- _load_env_file encoding ------------------------------------------------

def test_reads_a_utf8_bom_env_file_without_mangling_the_first_key(env_sandbox):
    tmp_path, _ = env_sandbox
    # Notepad and PowerShell's Set-Content both write UTF-8 with a BOM. Read
    # under the locale encoding the BOM became part of the first key's name,
    # so the setting silently vanished.
    (tmp_path / ".env").write_bytes("﻿MH_TEST_ALPHA=one\n".encode("utf-8"))
    cli._load_env_file()
    assert os.environ["MH_TEST_ALPHA"] == "one"


def test_an_undecodable_env_file_is_skipped_rather_than_crashing(env_sandbox):
    tmp_path, home = env_sandbox
    # UTF-16 raises UnicodeDecodeError, which is a ValueError — not an OSError,
    # so it used to escape the loader and crash at import time.
    (tmp_path / ".env").write_bytes("MH_TEST_ALPHA=utf16\n".encode("utf-16"))
    (home / ".make_harness").mkdir()
    _write_env(home / ".make_harness" / ".env", "MH_TEST_HOME=from-home\n")
    cli._load_env_file()
    assert os.environ["MH_TEST_HOME"] == "from-home"
    assert "MH_TEST_ALPHA" not in os.environ
