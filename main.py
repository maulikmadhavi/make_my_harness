"""Interactive REPL entry point for the harness."""

import os

# Importing a toolset registers its tools with the shared registry.
import harness.toolsets.fs  # noqa: F401
import harness.toolsets.shell  # noqa: F401
from harness.llm import LLMClient
from harness.log import RunLog
from harness.loop import run_turn
from harness.policy import Policy
from harness.tools import registry

SYSTEM_PROMPT = (
    "You are a helpful coding agent running in a minimal local harness on the user's "
    f"machine (Windows, working directory: {os.getcwd()}). "
    "Use your tools to read/write files and run commands when the task needs it. "
    "Keep answers concise."
)


def main():
    llm = LLMClient()
    log = RunLog()
    policy = Policy()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    tool_names = ", ".join(t["function"]["name"] for t in registry.schemas())
    print(f"harness REPL — {llm.model} — logging to {log.path}")
    print(f"tools: {tool_names}")
    print("type 'exit' or Ctrl+C to quit")

    while True:
        try:
            user = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit"):
            break

        log.event("user_message", content=user)
        messages.append({"role": "user", "content": user})
        try:
            answer = run_turn(llm, registry, policy, log, messages)
            print(f"\nagent > {answer}")
        except Exception as e:
            log.event("error", error=f"{type(e).__name__}: {e}")
            print(f"[error] {e}")


if __name__ == "__main__":
    main()
