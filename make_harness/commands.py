"""REPL slash commands (/clear, /compact, /exit) — handled locally, never
sent to the LLM. A small registry mirroring tools.py's @tool decorator, so
adding a new command means writing one function, not another elif in
cli.py. This was flagged as premature during the Stage 7 feedback review
(no slash commands existed yet to design around); /clear is the first one,
so the trigger for a pluggable mechanism is now real.
"""

from make_harness import compact as compaction
from make_harness import history

_COMMANDS = {}


def command(func):
    _COMMANDS[func.__name__] = func
    return func


def run(text, messages, log, llm=None):
    """Execute a /command. Returns (new_messages, output_text), where
    new_messages is None when the command ends the session (/exit).

    Every command is called as func(messages, llm, log); only commands
    that call the model (/compact) use llm.
    """
    name = text[1:].split(None, 1)[0] if len(text) > 1 else ""
    if name not in _COMMANDS:
        available = ", ".join(f"/{n}" for n in sorted(_COMMANDS)) or "(none)"
        return messages, f"Unknown command: /{name} — available: {available}"
    new_messages, output = _COMMANDS[name](messages, llm, log)
    log.event("command", name=name, output=output)
    return new_messages, output


@command
def clear(messages, llm, log):
    """Clear the conversation history, keeping the system prompt (and the
    memory/skills index folded into it) so context isn't lost."""
    return [messages[0]], "Conversation cleared — system prompt and memory/skills index kept."


@command
def compact(messages, llm, log):
    """Summarize the older part of the conversation now, instead of waiting
    for it to cross COMPACT_AT of the context window. The REPL also calls
    this after a turn that crossed it. The original comes back unchanged
    when the summary call fails — the window is nearly full, the worst
    moment to lose the conversation to a rate limit."""
    before = history.estimate(messages)
    try:
        new_messages = compaction.compact(messages, llm, log)
    except Exception as e:
        return messages, f"Compaction failed, conversation unchanged: {type(e).__name__}: {e}"
    if new_messages is None:
        return messages, f"Nothing old enough to compact yet (~{before} tokens)."
    if new_messages is messages:
        return messages, f"The summary came out no smaller than the history it would replace; kept the original (~{before} tokens)."
    return new_messages, f"Compacted: ~{before} -> ~{history.estimate(new_messages)} tokens."


@command
def exit(messages, llm, log):
    """End the session, like typing exit or quit. None in place of the
    message list is how a command tells the REPL to stop."""
    return None, "Goodbye."
