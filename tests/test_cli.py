"""Tests for cli — startup wiring and the argparse entry point.

The CLI flags and the piped-stdin REPL are driven end to end in a
subprocess. The .env loader lives in config (tests/test_config.py).
"""

import os
import platform
import subprocess
import sys

import pytest

from make_harness import __version__, cli
from make_harness.tools import registry

BACKEND_KEYS = ("BASE_URL", "API_KEY", "MODEL")
# An endpoint nothing listens on: any LLM round-trip surfaces as "error:".
UNREACHABLE = {"BASE_URL": "http://127.0.0.1:9/v1", "MODEL": "stub"}


class TestStartupWiring:
    def test_registers_the_documented_toolset(self):
        names = {t["function"]["name"] for t in registry.schemas()}
        assert {
            "read_file", "write_file", "str_replace", "run_command", "load_skill", "write_todos",
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
        # as '﻿exit' and it said goodbye).
        proc = _run_cli(
            cwd=tmp_path, stdin=b"\xef\xbb\xbfexit\r\n", **UNREACHABLE,
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        assert "make-harness" in out  # banner printed
        assert "error:" not in out  # exited before any LLM round-trip

    def test_resume_continues_the_last_chat_in_this_directory(self, tmp_path):
        # The first run's turn fails against the unreachable endpoint, but the
        # message it sent is still saved, which is all --resume needs.
        home = tmp_path / "home"
        project = tmp_path / "project"
        project.mkdir()
        dirs = {"HOME": str(home), "USERPROFILE": str(home)}
        first = _run_cli(cwd=project, stdin=b"remember the blue door\nexit\n", **UNREACHABLE, **dirs)
        assert first.returncode == 0
        second = _run_cli("--resume", cwd=project, stdin=b"exit\n", **UNREACHABLE, **dirs)
        out = second.stdout.decode("utf-8", errors="replace")
        assert second.returncode == 0
        assert "resumed " in out
        assert "you > remember the blue door" in out

    def test_resume_with_nothing_saved_starts_fresh(self, tmp_path):
        home = tmp_path / "home"
        proc = _run_cli("--resume", cwd=tmp_path, stdin=b"exit\n", **UNREACHABLE, HOME=str(home), USERPROFILE=str(home))
        assert proc.returncode == 0
        assert "No saved chat for this directory yet" in proc.stdout.decode("utf-8", errors="replace")

    def test_piped_slash_exit_stops_before_later_input(self, tmp_path):
        # End of input would stop the REPL on its own, so a bare "/exit"
        # could not show it worked; the "hello" after it would reach the
        # unreachable endpoint and print "error:" if the session carried on.
        proc = _run_cli(
            cwd=tmp_path, stdin=b"/exit\nhello\n", **UNREACHABLE,
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        assert proc.returncode == 0
        assert "Goodbye." in out
        assert "error:" not in out
