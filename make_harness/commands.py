"""REPL slash commands (/clear, /compact, /exit) — handled locally, never
sent to the LLM. A small registry mirroring tools.py's @tool decorator, so
adding a new command means writing one function, not another elif in
cli.py. This was flagged as premature during the Stage 7 feedback review
(no slash commands existed yet to design around); /clear is the first one,
so the trigger for a pluggable mechanism is now real.
"""

import copy

from make_harness import context

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
    """Compact the conversation now rather than at HARNESS_TOKEN_BUDGET.
    budget=1 is one nothing fits under, so every compaction step runs. It
    works on a copy, and hands back the original when the call fails
    (cli.py runs commands outside the turn's try) or when the result is no
    smaller — a summary of a short history can outgrow it."""
    before = context.estimate_tokens(messages)
    try:
        new_messages = context.compact(copy.deepcopy(messages), llm, log, budget=1)
    except Exception as e:
        return messages, f"Compaction failed, conversation unchanged: {type(e).__name__}: {e}"
    after = context.estimate_tokens(new_messages)
    if after >= before:
        return messages, f"Nothing to compact (~{before} tokens)."
    return new_messages, f"Compacted: ~{before} -> ~{after} tokens."


@command
def exit(messages, llm, log):
    """End the session, like typing exit or quit. None in place of the
    message list is how a command tells the REPL to stop."""
    return None, "Goodbye."
