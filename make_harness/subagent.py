"""Subagents: exploration in a context window of its own.

`task` runs run_turn — the same loop the main agent runs — on a brand-new
message list: a system prompt and the question, nothing else. The tool
output it reads along the way never reaches the main transcript; only its
final answer does. Exploring a codebase can burn tens of thousands of tokens
of tool output to produce a few hundred tokens of answer. Compaction throws
context away after it is spent; a subagent spends it in a list that is
discarded by design.

It shares the main agent's LLM, permission gate and log (its events tagged
agent=subagent), so it is fenced in by the same rules, and it is offered
every tool except WITHHELD — a structural limit, not a request in a prompt.
"""

import os
import platform

from make_harness.loop import TURN_DENIED, run_turn
from make_harness.tools import registry, tool
from make_harness.ui import dim

MAX_STEPS = 12  # a runaway explorer is worse than a missing answer

# task: no subagents spawning subagents. write_todos: the plan belongs to the
# main agent. The rest write; a subagent reads and reports.
WITHHELD = {"task", "write_todos", "write_file", "str_replace", "save_memory"}

SYSTEM_PROMPT = """\
You are an exploration subagent on {os}, working in {cwd}. A lead agent sent \
you one question. Answer it, then stop.

You cannot see the lead agent's conversation, and it sees nothing you do \
except your final message, so that message must stand on its own.

- Find out what is actually true with your tools. Search inside the working \
directory, never from the drive root or the home directory.
- Read and report; change nothing, and run no commands with side effects.
- Batch your searches: several tool calls in one step beat one per step.
- Stop as soon as you can answer.

Your final message is the whole report, and it is all the lead agent pays \
for, so keep it under about 150 words. Findings only: file paths with line \
numbers, names, values. No preamble and no long code blocks — cite where \
things are instead. Say plainly what you could not find."""

_runtime = {}  # llm, policy, log — set by configure() once the REPL has them


def configure(llm, policy, log):
    """Hand `task` the session's LLM, permission gate and log."""
    _runtime.update(llm=llm, policy=policy, log=log)


class _Tagged:
    """A log that marks every event as the subagent's."""

    def __init__(self, log):
        self.log = log

    def event(self, kind, **data):
        self.log.event(kind, agent="subagent", **data)


def _last_words(messages):
    return next(
        (m["content"] for m in reversed(messages) if m["role"] == "assistant" and m.get("content")), None
    )


@tool
def task(description: str) -> str:
    """Send a self-contained question about the codebase to a subagent with its own context window, and get back only its findings. Use it to learn how something works — where a feature lives, how data flows, what calls what — so the search costs you one answer instead of many tool results. It cannot see this conversation, so say everything it needs: what to find, where to start, what the answer should contain. It only reads; do your own editing."""
    if not _runtime:
        return "Error: subagents are only available inside the REPL."
    log = _Tagged(_runtime["log"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(os=platform.system(), cwd=os.getcwd())},
        {"role": "user", "content": description},
    ]
    print(dim(f"  ⤷ subagent: {' '.join(description.split())[:100]}"))
    log.event("subagent_start", description=description)
    report = run_turn(
        _runtime["llm"], registry.without(WITHHELD), _runtime["policy"], log, messages,
        max_steps=MAX_STEPS, indent="    ",
    )
    if report == TURN_DENIED:
        report = "(the subagent stopped: the user denied one of its tool calls)"
    elif report is not None and report.startswith("[stopped:"):
        partial = _last_words(messages)
        report = (
            f"(the subagent stopped after {MAX_STEPS} steps without finishing"
            + (f"; its partial findings follow — narrow the question to go further)\n\n{partial}" if partial else ")")
        )
    report = report or "(the subagent came back with nothing)"
    log.event("subagent_done", report=report)
    print(dim("  ⤶ subagent done"))
    return report
