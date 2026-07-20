"""Interactive REPL entry point for the harness."""

import argparse
import os
import platform
import sys

# Importing a toolset registers its tools with the shared registry.
import make_harness.toolsets.fs  # noqa: F401
import make_harness.toolsets.shell  # noqa: F401
import make_harness.toolsets.web  # noqa: F401
from make_harness import __version__
from make_harness.context import compact
from make_harness.llm import LLMClient
from make_harness.mentions import expand_mentions
from make_harness.toolsets.memory import memory_index
from make_harness.log import RunLog
from make_harness.loop import run_turn
from make_harness.policy import Policy
from make_harness.prompt import make_input
from make_harness.tools import registry
from make_harness.ui import bold, cyan, dim, green, red

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
    messages = [{"role": "system", "content": system}]
    tool_names = ", ".join(t["function"]["name"] for t in registry.schemas())
    print(f"{bold(cyan('make-harness'))} {dim('v' + __version__)} — {llm.model}")
    print(dim(f"log:   {log.path}"))
    print(dim(f"tools: {tool_names}"))
    print(dim("@path attaches a file or folder — type @ for a picker (Tab/arrows select)"))
    print(dim("type 'exit' or Ctrl+C to quit"))
    read_input = make_input()

    while True:
        try:
            user = read_input(f"\n{bold(cyan('you >'))} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit"):
            break

        expanded, attached = expand_mentions(user)
        for mention in attached:
            print(dim(f"  @ attached {mention}"))
        log.event("user_message", content=user, attachments=attached)
        messages.append({"role": "user", "content": expanded})
        try:
            messages = compact(messages, llm, log)
            answer = run_turn(llm, registry, policy, log, messages)
            print(f"\n{bold(green('agent >'))} {answer}")
        except Exception as e:
            log.event("error", error=f"{type(e).__name__}: {e}")
            print(red(f"[error] {e}"))


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
