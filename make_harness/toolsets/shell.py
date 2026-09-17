import subprocess

from make_harness import sandbox
from make_harness.history import cap
from make_harness.tools import tool

TIMEOUT = 60


@tool
def run_command(command: str) -> str:
    """Run a shell command and return its exit code and output (stdout + stderr)."""
    try:
        proc = sandbox.run(command, TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {TIMEOUT}s"
    out = cap((proc.stdout + proc.stderr).strip())
    return f"exit code: {proc.returncode}\n{out}" if out else f"exit code: {proc.returncode} (no output)"
