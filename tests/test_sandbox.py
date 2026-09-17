"""Tests for sandbox — when bubblewrap is used, the argv it builds, and (on
a Linux machine with bwrap installed) what a sandboxed command can and
cannot do."""

import sys
from pathlib import Path

import pytest

from make_harness import sandbox


@pytest.mark.parametrize(
    "platform,bwrap,expected",
    [("linux", "/usr/bin/bwrap", True), ("linux", None, False), ("win32", "/usr/bin/bwrap", False), ("darwin", None, False)],
    ids=["linux-with-bwrap", "linux-without", "windows", "macos"],
)
def test_available_only_on_linux_with_bwrap(monkeypatch, platform, bwrap, expected):
    monkeypatch.setattr(sandbox.sys, "platform", platform)
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: bwrap)
    assert sandbox.available() is expected
    assert sandbox.name() == ("bubblewrap" if expected else "none")


def test_no_sandbox_means_no_wrapping(monkeypatch):
    monkeypatch.setattr(sandbox, "available", lambda: False)
    assert sandbox.wrap("ls") is None


def test_wrap_builds_the_bubblewrap_argv(monkeypatch):
    monkeypatch.setattr(sandbox, "available", lambda: True)
    argv = sandbox.wrap("ls -la", project="/work/proj")
    assert argv[0] == "bwrap"
    assert argv[-3:] == ["/bin/sh", "-c", "ls -la"]
    assert argv[argv.index("--ro-bind") + 1: argv.index("--ro-bind") + 3] == ["/", "/"]
    assert argv[argv.index("--bind") + 1: argv.index("--bind") + 3] == ["/work/proj", "/work/proj"]
    assert argv.index("--tmpfs") < argv.index("--bind")  # a project under /tmp stays writable
    assert argv[argv.index("--chdir") + 1] == "/work/proj"
    assert {"--unshare-net", "--new-session", "--die-with-parent"} <= set(argv)


def test_unsandboxed_run_goes_through_the_shell(monkeypatch):
    monkeypatch.setattr(sandbox, "available", lambda: False)
    proc = sandbox.run(f'"{sys.executable}" -c "print(6 * 7)"', timeout=30)
    assert (proc.returncode, proc.stdout.strip()) == (0, "42")


needs_bwrap = pytest.mark.skipif(not sandbox.available(), reason="needs Linux with bubblewrap installed")


@needs_bwrap
class TestRealBubblewrap:
    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_writes_inside_the_project(self, project):
        proc = sandbox.run("echo hi > inside.txt && cat inside.txt", timeout=30)
        assert (proc.returncode, proc.stdout.strip()) == (0, "hi")
        assert (project / "inside.txt").read_text() == "hi\n"

    def test_cannot_write_outside_the_project(self, project):
        # Not under /tmp: inside the sandbox that is a writable throwaway tmpfs.
        target = Path.home() / ".make-harness-sandbox-escape"
        try:
            proc = sandbox.run(f"echo x > {target}", timeout=30)
            assert proc.returncode != 0
            assert not target.exists()
        finally:
            target.unlink(missing_ok=True)

    def test_tmp_is_a_throwaway(self, project):
        proc = sandbox.run("echo x > /tmp/make-harness-sandbox-probe && cat /tmp/make-harness-sandbox-probe", timeout=30)
        assert (proc.returncode, proc.stdout.strip()) == (0, "x")  # writable inside
        assert not Path("/tmp/make-harness-sandbox-probe").exists()  # gone outside

    def test_has_no_network(self, project):
        probe = "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)"
        proc = sandbox.run(f"python3 -c \"{probe}\"", timeout=30)
        assert proc.returncode != 0
