"""REPL slash commands — handled locally, never sent to the LLM.

A small registry mirroring tools.py's @tool decorator: adding a command
means writing one function, not another elif in cli.py. Every command is
called as func(messages, ctx) and returns (new_messages, output), where
new_messages is None when the command ends the REPL (/exit).

ctx bundles what commands reach for beyond the message list: the log, the
LLM (/compact), the saved session (/sessions, /rewind, and every command
that changes history has to record it there), a chooser for picking from a
list, and the current system prompt.
"""

from dataclasses import dataclass

from make_harness import compact as compaction
from make_harness import history
from make_harness.session import preview, title
from make_harness.toolsets import todos

_COMMANDS = {}


@dataclass
class Context:
    log: object
    llm: object = None
    session: object = None  # session.Session; None when nothing is saved
    ask: object = None  # ask(prompt_text, [(value, label), ...]) -> value
    system_prompt: str = ""


def command(func):
    _COMMANDS[func.__name__] = func
    return func


def run(text, messages, ctx):
    """Execute a /command. Returns (new_messages, output_text), where
    new_messages is None when the command ends the session (/exit)."""
    name = text[1:].split(None, 1)[0] if len(text) > 1 else ""
    if name not in _COMMANDS:
        available = ", ".join(f"/{n}" for n in sorted(_COMMANDS)) or "(none)"
        return messages, f"Unknown command: /{name} — available: {available}"
    new_messages, output = _COMMANDS[name](messages, ctx)
    ctx.log.event("command", name=name, output=output)
    return new_messages, output


def reopen(messages, ctx):
    """Make a loaded transcript current: today's system prompt in place of
    the one it was saved with (skills and memory may have changed), and tool
    results shortened again, since the file keeps them in full."""
    messages = [{"role": "system", "content": ctx.system_prompt}] + messages[1:]
    history.strip(messages)
    return messages


def _pick(ctx, prompt_text, choices):
    """The chosen value, or None when there is no chooser or the user bails."""
    if ctx.ask is None:
        return None
    try:
        return ctx.ask(prompt_text, choices + [("cancel", "Cancel")])
    except (EOFError, KeyboardInterrupt):
        return None


@command
def clear(messages, ctx):
    """Clear the conversation history and the todo list, keeping the system
    prompt (and the memory/skills index folded into it) so context isn't
    lost. The cleared chat stays saved; what follows goes to a new session."""
    todos.clear()
    if ctx.session:
        ctx.session.start_new()
    return [messages[0]], "Conversation cleared — system prompt and memory/skills index kept."


@command
def compact(messages, ctx):
    """Summarize the older part of the conversation now, instead of waiting
    for it to cross COMPACT_AT of the context window. The REPL also calls
    this after a turn that crossed it. The original comes back unchanged
    when the summary call fails — the window is nearly full, the worst
    moment to lose the conversation to a rate limit."""
    before = history.estimate(messages)
    try:
        new_messages = compaction.compact(messages, ctx.llm, ctx.log)
    except Exception as e:
        return messages, f"Compaction failed, conversation unchanged: {type(e).__name__}: {e}"
    if new_messages is None:
        return messages, f"Nothing old enough to compact yet (~{before} tokens)."
    if new_messages is messages:
        return messages, f"The summary came out no smaller than the history it would replace; kept the original (~{before} tokens)."
    if ctx.session:
        ctx.session.replace(new_messages)
    return new_messages, f"Compacted: ~{before} -> ~{history.estimate(new_messages)} tokens."


@command
def sessions(messages, ctx):
    """Open another saved chat from this project."""
    saved = [s for s in ctx.session.list() if s["id"] != ctx.session.id] if ctx.session else []
    if not saved:
        return messages, "No other saved chats for this project."
    choices = [(str(n), f"{s['id']}  {s['title']}  ({s['messages']} messages)") for n, s in enumerate(saved, 1)]
    choice = _pick(ctx, "open chat: ", choices)
    if choice in (None, "cancel"):
        return messages, "Kept the current chat."
    chosen = saved[int(choice) - 1]
    opened = reopen(ctx.session.open(chosen["id"]), ctx)
    todos.clear()
    return opened, f"Opened {chosen['id']} ({len(opened)} messages).\n{preview(opened)}"


@command
def rewind(messages, ctx):
    """Go back to before one of your earlier messages, dropping it and
    everything after it. The saved file keeps the dropped part."""
    points = [
        i for i, m in enumerate(messages)
        if m["role"] == "user" and not (m.get("content") or "").startswith(history.SUMMARY)
    ][::-1][:20]  # the 20 most recent, newest first
    if not points:
        return messages, "Nothing to rewind yet."
    choices = [(str(n), title([messages[i]])) for n, i in enumerate(points, 1)]
    choice = _pick(ctx, "rewind to before: ", choices)
    if choice in (None, "cancel"):
        return messages, "Nothing rewound."
    index = points[int(choice) - 1]
    if ctx.session:
        ctx.session.rewind_to(index)
    return messages[:index], f"Rewound to before: {title([messages[index]])} ({index} messages kept)."


@command
def exit(messages, ctx):
    """End the session, like typing exit or quit. None in place of the
    message list is how a command tells the REPL to stop."""
    return None, "Goodbye."
