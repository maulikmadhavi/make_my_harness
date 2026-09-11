"""Interactive entry point for the harness: the Rich-styled text REPL."""

import argparse
import os
import platform
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text


def _load_env_file():
    """Load .env file if it exists (project root).

    Skipped if: GROQ_API_KEY is set (test override), or MAKE_HARNESS_NO_ENV is set.
    """
    # Skip if explicitly disabled or running in test with GROQ_API_KEY override
    if os.getenv("MAKE_HARNESS_NO_ENV"):
        return

    # Try multiple locations for .env file
    candidates = [
        ".env",  # Current working directory
        os.path.expanduser("~/.make_harness/.env"),  # User home
        os.path.join(os.path.dirname(__file__), "..", ".env"),  # Project root relative to this file
    ]

    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            key, _, value = line.partition("=")
                            key = key.strip()
                            value = value.strip().strip("\"'")
                            # Don't override existing env vars, especially GROQ_API_KEY
                            if key and not os.getenv(key):
                                os.environ[key] = value
                break  # Stop after first successful load
            except (IOError, OSError):
                continue


_load_env_file()

# Rich console for polished output
console = Console()

# Importing a toolset registers its tools with the shared registry.
import make_harness.toolsets.fs  # noqa: F401
import make_harness.toolsets.shell  # noqa: F401
import make_harness.toolsets.skills  # noqa: F401
import make_harness.toolsets.web  # noqa: F401
from make_harness import __version__
from make_harness import commands
from make_harness.context import compact
from make_harness.llm import LLMClient
from make_harness.mentions import expand_mentions
from make_harness.toolsets.memory import memory_index
from make_harness.toolsets.skills import skills_index
from make_harness.log import RunLog
from make_harness.loop import run_turn
from make_harness.policy import Policy
from make_harness.prompt import make_input
from make_harness.tools import registry
from make_harness.ui import bold, cyan

SYSTEM_PROMPT = (
    "You are a helpful coding agent running in a minimal local harness on the user's "
    f"machine ({platform.system()}, working directory: {os.getcwd()}). "
    "Use shell commands appropriate for this OS. "
    "Use your tools to read/write files and run commands when the task needs it. "
    "If a tool returns an error, report it to the user honestly — never invent a "
    "result you did not get from a tool. Keep answers concise."
)


def repl():
    if not sys.stdin.isatty():
        # Piped input: decode as UTF-8 and swallow a leading BOM —
        # PowerShell 5.1 pipes one in, and under the default cp1252
        # decoding 'exit' arrives as 'ï»¿exit' and misses the exit check
        # (found live: the model politely said goodbye instead).
        sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
    llm = LLMClient()
    log = RunLog()
    policy = Policy()
    system = SYSTEM_PROMPT
    index = memory_index()
    if index:
        system += "\n\nPersistent memory index (use read_memory for details):\n" + index
    skills = skills_index()
    if skills:
        system += "\n\nAvailable skills (use load_skill for full instructions):\n" + skills
    messages = [{"role": "system", "content": system}]
    tool_names = ", ".join(t["function"]["name"] for t in registry.schemas())

    # Rich formatted header
    console.print()
    console.print(
        Panel(
            f"[bold cyan]make-harness[/bold cyan] [dim]v{__version__}[/dim] • [cyan]{llm.model}[/cyan]",
            expand=False,
            border_style="cyan",
        )
    )
    console.print(f"[dim]log:   {log.path}[/dim]")
    console.print(f"[dim]tools: {tool_names}[/dim]")
    console.print()
    console.print("[dim]Shortcuts:[/dim]")
    console.print("  [cyan]@path[/cyan]     Attach files/folders")
    console.print("  [cyan]/clear[/cyan]    Reset conversation (memory kept)")
    console.print("  [cyan]exit[/cyan]      Quit")
    console.print()
    read_input = make_input()

    while True:
        try:
            # read_input is prompt_toolkit (expects ANSI codes, not rich markup)
            user = read_input(f"\n{bold(cyan('you >'))} ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit"):
            break
        if user.startswith("/"):
            messages, output = commands.run(user, messages, log)
            console.print(f"[dim]{escape(output)}[/dim]")
            continue

        expanded, attached = expand_mentions(user)
        for mention in attached:
            console.print(f"[dim]  @ attached {escape(mention)}[/dim]")
        log.event("user_message", content=user, attachments=attached)
        messages.append({"role": "user", "content": expanded})
        try:
            messages = compact(messages, llm, log)
            answer = run_turn(llm, registry, policy, log, messages)
            console.print()
            # Text() keeps the answer literal — brackets in code like
            # list[int] must not be parsed as rich markup.
            console.print(
                Panel(Text(answer or ""), title="[bold green]agent[/bold green]", border_style="green", expand=False)
            )
        except Exception as e:
            log.event("error", error=f"{type(e).__name__}: {e}")
            console.print(f"[bold red]error:[/bold red] {escape(str(e))}")


def main():
    parser = argparse.ArgumentParser(
        prog="make-harness",
        description="A minimal, bottom-up agent harness with pluggable tools, "
        "permissions, memory, and context compaction.",
    )
    parser.add_argument("--version", action="version", version=f"make-harness {__version__}")
    parser.parse_args()

    repl()


if __name__ == "__main__":
    main()
