"""OS-enforced limits on what run_command can touch — Linux only.

One policy: read anything, write only inside the project directory (plus a
throwaway /tmp), no network. On Linux, bubblewrap (bwrap) enforces it when
it is installed. Elsewhere commands run unsandboxed: this project targets
win-64 and linux-64, and Windows has no equivalent a user can run without
admin rights — there the rules in policy.py are the only fence.

The two layers do different jobs: policy.py decides which commands are
worth asking the user about; the sandbox decides what a command can do
even after a yes.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def available():
    return sys.platform.startswith("linux") and shutil.which("bwrap") is not None


def name():
    return "bubblewrap" if available() else "none"


def wrap(command, project=None):
    """The argv that runs `command` inside bubblewrap, or None without a sandbox."""
    if not available():
        return None
    project = str(project or Path.cwd().resolve())
    return [
        "bwrap",
        "--ro-bind", "/", "/",       # the whole filesystem, read-only
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",           # scratch space for tools like pytest, gone afterwards
        "--bind", project, project,  # after the tmpfs, so a project under /tmp stays writable
        "--chdir", project,
        "--unshare-net",
        "--new-session",             # no writing keystrokes back into the user's terminal
        "--die-with-parent",
        "/bin/sh", "-c", command,
    ]


def run(command, timeout):
    """Run a shell command, sandboxed when the OS allows it."""
    argv = wrap(command)
    return subprocess.run(
        argv or command, shell=argv is None, capture_output=True, text=True, timeout=timeout
    )
