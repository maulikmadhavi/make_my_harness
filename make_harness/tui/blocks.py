"""Pure data model for the TUI transcript.

Turns `messages` (the real OpenAI-format conversation) plus a parallel
`reasoning_events` list (one entry per assistant step, populated by
loop.run_turn's on_event hook — see Stage 15) into a flat list of
renderable Blocks, with fold state tracked per block id. No
prompt_toolkit import here: this stays testable with plain message-dict
fixtures, the same style tests/test_loop.py already uses.
"""

import os
from dataclasses import dataclass, field

FOLD_CHARS_ENV = "HARNESS_REASONING_FOLD_CHARS"
DEFAULT_FOLD_CHARS = 400


@dataclass
class Block:
    id: str
    kind: str  # "user" | "reasoning" | "tool" | "answer"
    text: str
    meta: dict = field(default_factory=dict)
    collapsible: bool = False
    collapsed: bool = False


def _fold_threshold():
    return int(os.getenv(FOLD_CHARS_ENV, str(DEFAULT_FOLD_CHARS)))


def build_blocks(messages, reasoning_events, folds):
    """Walk messages + reasoning_events into a flat list of Blocks.

    folds (dict[block_id, bool]) is mutated in place: a block id seen for
    the first time gets a length-based default fold state seeded in
    (reasoning text longer than HARNESS_REASONING_FOLD_CHARS, default
    400, starts collapsed); an id already present keeps whatever fold
    state was last set there, so a manual toggle survives across the many
    calls one live turn triggers. Only reasoning blocks are collapsible —
    tool/user/answer blocks always render in full.

    messages and reasoning_events are snapshotted (list(...)) at the top
    so a concurrent append from a worker thread can't produce a torn read
    mid-walk.
    """
    messages = list(messages)
    reasoning_events = list(reasoning_events)
    threshold = _fold_threshold()

    blocks = []
    assistant_step = 0
    counters = {"user": 0, "reasoning": 0, "answer": 0}

    i, n = 0, len(messages)
    while i < n:
        role = messages[i].get("role")

        if role == "system" or role == "tool":
            # Tool messages are consumed alongside their assistant
            # tool_calls entry below; a stray one (shouldn't happen given
            # the harness's own tool_call/tool pairing guarantee) is
            # skipped defensively rather than crashing the render.
            i += 1
            continue

        if role == "user":
            counters["user"] += 1
            block_id = f"user-{counters['user']}"
            blocks.append(Block(id=block_id, kind="user", text=messages[i].get("content") or ""))
            i += 1
            continue

        # role == "assistant"
        reasoning_text = reasoning_events[assistant_step] if assistant_step < len(reasoning_events) else None
        assistant_step += 1
        if reasoning_text:
            counters["reasoning"] += 1
            r_id = f"reasoning-{counters['reasoning']}"
            if r_id not in folds:
                folds[r_id] = len(reasoning_text) > threshold
            blocks.append(Block(
                id=r_id, kind="reasoning", text=reasoning_text,
                collapsible=True, collapsed=folds[r_id],
            ))

        tool_calls = messages[i].get("tool_calls")
        if tool_calls:
            results = {}
            j = i + 1
            while j < n and messages[j].get("role") == "tool":
                results[messages[j]["tool_call_id"]] = messages[j].get("content", "")
                j += 1
            for tc in tool_calls:
                blocks.append(Block(
                    id=tc["id"],
                    kind="tool",
                    text=results.get(tc["id"], ""),
                    meta={"tool": tc["function"]["name"], "args": tc["function"]["arguments"]},
                ))
            i = j
        else:
            counters["answer"] += 1
            a_id = f"answer-{counters['answer']}"
            blocks.append(Block(id=a_id, kind="answer", text=messages[i].get("content") or ""))
            i += 1

    return blocks
