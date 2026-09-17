"""Keeping the transcript small enough to send.

Three mechanisms, cheapest first; compact.py is the expensive fourth.

1. cap    A fresh tool result over CAP chars keeps its head and tail inline,
          and the whole text goes to a temp file named at the cut, so the
          agent can page through it with read_file. The file is deleted
          when the turn ends (sweep).
2. strip  Once a turn is over, its tool results shrink to STUB chars. The
          model has already acted on them, and it can run the tool again.
          Old messages only ever shrink at the end of a turn, so the prompt
          prefix stays stable for the server's prompt cache in between.
3. fit    A single request is still too big: drop whole tool results,
          oldest first, until the estimate fits the window.

strip and fit never touch the frozen prefix — everything up to and including
the newest compaction summary — so that block stays byte-identical, and
cached, until the next compaction.
"""

import json
import tempfile
from pathlib import Path

from make_harness import config
from make_harness.toolsets import truncate

CAP = 10_000  # chars of a fresh tool result shown inline
STUB = 300  # chars a tool result keeps once its turn is over

TRIMMED = "[trimmed:"  # marks a result already shrunk, so shrinking twice is a no-op
SUMMARY = "<summary>"  # opens the handoff note compaction leaves behind

_spills = []  # temp files belonging to the current turn


def estimate(messages):
    """Rough token count: ~4 characters per token."""
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) // 4


def _spill(text):
    """Save the whole text for the rest of this turn; return the file path."""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", prefix="make-harness-", suffix=".txt", delete=False
    ) as f:
        f.write(text)
    _spills.append(Path(f.name))
    return f.name


def cap(text):
    """Trim a fresh tool result to CAP chars, pointing at the whole of it."""
    if len(text) <= CAP:
        return text
    try:
        path = _spill(text)
    except OSError:
        return truncate(text, CAP) + "\n[the full output could not be saved]"
    return (
        truncate(text, CAP)
        + f"\n[full output ({len(text)} chars) saved to {path} — only the middle was cut, "
        "so if you need it, read that part with read_file offset/limit rather than "
        "running the tool again. The file is deleted when this turn ends.]"
    )


def sweep():
    """Delete this turn's temp files; the paths in its results die with them."""
    for path in _spills:
        path.unlink(missing_ok=True)
    _spills.clear()


def locked(messages):
    """Length of the frozen prefix: everything up to and including the
    newest summary. Derived each time rather than stored, so it stays right
    across /compact, /rewind and switching sessions."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message["role"] == "user" and (message.get("content") or "").startswith(SUMMARY):
            return index + 1
    return 0


def strip(messages):
    """Shrink every finished tool result outside the frozen prefix to STUB
    chars. Called when a turn ends. Returns how many shrank."""
    shrunk = 0
    for message in messages[locked(messages):]:
        content = message.get("content") or ""
        if message["role"] != "tool" or TRIMMED in content or len(content) <= STUB:
            continue
        message["content"] = (
            content[:STUB] + f"\n{TRIMMED} {len(content) - STUB} more chars from an "
            "earlier turn. Run the tool again if you need them.]"
        )
        shrunk += 1
    return shrunk


def fit(messages, budget=None):
    """Last resort before a request: replace whole tool results, oldest
    first, until the estimate is under budget. Returns how many went —
    normally zero, because cap and strip do the real work."""
    if budget is None:
        budget = config.CONTEXT_WINDOW * config.COMPACT_AT
    tokens = estimate(messages)
    dropped = 0
    for message in messages[locked(messages):]:
        if tokens <= budget:
            break
        content = message.get("content") or ""
        if message["role"] != "tool" or content.startswith(TRIMMED):
            continue
        message["content"] = f"{TRIMMED} dropped to fit the context window.]"
        tokens -= (len(content) - len(message["content"])) // 4
        dropped += 1
    return dropped
