"""Interactive REPL entry point for the harness.

Stage 22: Uses full-screen TUI (make_harness/tui/app.py) for prettier output.
"""

import argparse
import os
import platform
import sys
import threading
from queue import Queue, Empty

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
from make_harness.ui import bold, cyan, dim, green, red
from make_harness.tui.app import TranscriptState, build_application
from make_harness.tui.blocks import build_blocks

SYSTEM_PROMPT = (
    "You are a helpful coding agent running in a minimal local harness on the user's "
    f"machine ({platform.system()}, working directory: {os.getcwd()}). "
    "Use shell commands appropriate for this OS. "
    "Use your tools to read/write files and run commands when the task needs it. "
    "If a tool returns an error, report it to the user honestly — never invent a "
    "result you did not get from a tool. Keep answers concise."
)


def run_tui_repl():
    """Stage 22: Full-screen TUI REPL with live transcript and input box.

    Uses threading to run the agent loop in the background while the TUI
    remains responsive to user input.
    """
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

    # TUI state
    reasoning_events = []  # Populated by on_event callback
    state = TranscriptState(blocks=[], folds={})

    # Thread-safe queue for agent results
    agent_queue = Queue()

    def update_transcript():
        """Rebuild transcript from messages + reasoning."""
        blocks = build_blocks(messages, reasoning_events, state.folds)
        state.blocks = blocks
        state.focused_index = len(blocks) - 1 if blocks else -1

    def on_event(kind, **kwargs):
        """Callback from run_turn to capture reasoning."""
        if kind == "reasoning":
            reasoning_events.append(kwargs.get("text", ""))
        update_transcript()

    def run_agent_thread(user_input):
        """Run the agent loop in a background thread."""
        try:
            log.event("user_message", content=user_input, attachments=[])
            messages.append({"role": "user", "content": user_input})

            messages_before = len(messages)
            messages[:] = compact(messages, llm, log)
            answer = run_turn(
                llm, registry, policy, log, messages,
                on_event=on_event
            )
            update_transcript()
            agent_queue.put(("done", None))
        except Exception as e:
            log.event("error", error=f"{type(e).__name__}: {e}")
            agent_queue.put(("error", str(e)))

    def on_submit(text):
        """Handle user input submission."""
        if text.lower() in ("exit", "quit"):
            # Signal exit to the app
            agent_queue.put(("exit", None))
            return

        if text.startswith("/"):
            messages[:], output = commands.run(text, messages, log)
            update_transcript()
            return

        # Expand @mentions
        expanded, attached = expand_mentions(text)
        for mention in attached:
            log.event("mention", attachment=mention)

        # Run agent in background thread
        threading.Thread(target=run_agent_thread, args=(expanded,), daemon=True).start()

    app = build_application(state, on_submit=on_submit)

    # Run the app (blocking until user quits)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


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
    print(f"{bold(cyan('make-harness'))} {dim('v' + __version__)} — {llm.model}")
    print(dim(f"log:   {log.path}"))
    print(dim(f"tools: {tool_names}"))
    print(dim("@path attaches a file or folder — type @ for a picker (Tab/arrows select)"))
    print(dim("/clear resets the conversation (memory/skills index kept)"))
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
        if user.startswith("/"):
            messages, output = commands.run(user, messages, log)
            print(dim(output))
            continue

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
    parser.add_argument(
        "--no-tui", action="store_true",
        help="Use classic text REPL instead of full-screen TUI"
    )
    args = parser.parse_args()

    # Stage 22: Use TUI by default, fall back to text REPL with --no-tui
    if args.no_tui:
        repl()
    else:
        run_tui_repl()


if __name__ == "__main__":
    main()
