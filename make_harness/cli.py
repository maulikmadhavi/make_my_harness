"""Interactive entry point for the harness: the Rich-styled text REPL."""

import argparse
import os
import platform
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

# Imported first, before any other harness module: it loads the .env file at
# import time, and settings like config.CONTEXT_WINDOW and ui.ENABLED are read
# at import time too.
import make_harness.config  # noqa: F401, E402

# Importing a toolset registers its tools with the shared registry.
import make_harness.toolsets.fs  # noqa: F401
import make_harness.toolsets.shell  # noqa: F401
import make_harness.toolsets.skills  # noqa: F401
import make_harness.toolsets.web  # noqa: F401
from make_harness import __version__
from make_harness import commands, history
from make_harness.compact import needed as compaction_needed
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
    "Edit existing files with str_replace; use write_file only to create a file or "
    "replace all of it. "
    "Long tool output is cut down, and the full text saved to a temp file named at "
    "the cut: page through it with read_file offset/limit instead of running the "
    "tool again. That file is deleted when your turn ends, and tool results from "
    "earlier turns are shortened — run the tool again if you need one in full. "
    "If a tool returns an error, report it to the user honestly — never invent a "
    "result you did not get from a tool. Keep answers concise."
)


def repl():
    # Built here rather than at module scope so `--version` doesn't pay for it,
    # and so make_harness.ui (imported above) has already switched the legacy
    # Windows console into VT mode before rich caches its render-path decision.
    console = Console()
    if not sys.stdin.isatty():
        # Piped input: decode as UTF-8 and swallow a leading BOM —
        # PowerShell 5.1 pipes one in, and under the default cp1252
        # decoding 'exit' arrives as 'ï»¿exit' and misses the exit check
        # (found live: the model politely said goodbye instead).
        sys.stdin.reconfigure(encoding="utf-8-sig", errors="replace")
    try:
        llm = LLMClient()
    except RuntimeError as e:  # no backend configured: say what to set, no traceback
        sys.exit(f"error: {e}")
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
    console.print("  [cyan]/compact[/cyan]  Summarize history to free context")
    console.print("  [cyan]/exit[/cyan]     Quit (exit and quit work too)")
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
            new_messages, output = commands.run(user, messages, log, llm)
            console.print(f"[dim]{escape(output)}[/dim]")
            if new_messages is None:
                break
            messages = new_messages
            continue

        expanded, attached = expand_mentions(user)
        for mention in attached:
            console.print(f"[dim]  @ attached {escape(mention)}[/dim]")
        log.event("user_message", content=user, attachments=attached)
        messages.append({"role": "user", "content": expanded})
        try:
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
        finally:
            # The turn is over: bin its temp files and shrink the tool output
            # it produced (history.py).
            history.sweep()
            history.strip(messages)
        if compaction_needed(llm.last_usage, messages):
            messages, output = commands.compact(messages, llm, log)
            console.print(f"[dim]{escape(output)}[/dim]")


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
