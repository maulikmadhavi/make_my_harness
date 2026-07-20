"""REPL slash commands (/clear, ...) — handled locally, never sent to the
LLM. A small registry mirroring tools.py's @tool decorator, so adding a
new command means writing one function, not another elif in cli.py. This
was flagged as premature during the Stage 7 feedback review (no slash
commands existed yet to design around); /clear is the first one, so the
trigger for a pluggable mechanism is now real.
"""

_COMMANDS = {}


def command(func):
    _COMMANDS[func.__name__] = func
    return func


def run(text, messages, log):
    """Execute a /command. Returns (new_messages, output_text)."""
    name = text[1:].split(None, 1)[0] if len(text) > 1 else ""
    if name not in _COMMANDS:
        available = ", ".join(f"/{n}" for n in sorted(_COMMANDS)) or "(none)"
        return messages, f"Unknown command: /{name} — available: {available}"
    new_messages, output = _COMMANDS[name](messages)
    log.event("command", name=name, output=output)
    return new_messages, output


@command
def clear(messages):
    """Clear the conversation history, keeping the system prompt (and the
    memory/skills index folded into it) so context isn't lost."""
    return [messages[0]], "Conversation cleared — system prompt and memory/skills index kept."
