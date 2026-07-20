import subprocess

from make_harness.tools import tool
from make_harness.toolsets import truncate

MAX_OUTPUT = 10_000
TIMEOUT = 60


@tool
def run_command(command: str) -> str:
    """Run a shell command and return its exit code and output (stdout + stderr)."""
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {TIMEOUT}s"
    out = truncate((proc.stdout + proc.stderr).strip(), MAX_OUTPUT)
    return f"exit code: {proc.returncode}\n{out}" if out else f"exit code: {proc.returncode} (no output)"
