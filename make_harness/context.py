"""Context management: keep the conversation under a token budget.

Two-step compaction when over budget:
1. Stub old tool results (cheap, keeps conversation structure intact).
2. Summarize everything between the system prompt and the recent window
   with one LLM call and replace it with a single summary message.
The system prompt and the most recent messages are never touched.
"""

import json
import os

TOKEN_BUDGET = int(os.getenv("HARNESS_TOKEN_BUDGET", "60000"))
KEEP_RECENT = 8
STUB_LEN = 200

SUMMARY_PROMPT = (
    "Summarize this agent conversation so it can continue seamlessly. "
    "Keep: user goals, decisions made, file paths touched, tool results that "
    "still matter, and unfinished work."
)


def estimate_tokens(messages):
    """Rough estimate: ~4 characters per token."""
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) // 4


def _safe_cut(messages, index):
    """Move a cut point forward so it never separates an assistant
    tool_calls message from its following tool results."""
    while index < len(messages) and messages[index]["role"] == "tool":
        index += 1
    return index


def _stub_tools(msgs):
    changed = False
    for m in msgs:
        if m["role"] == "tool" and len(m.get("content") or "") > STUB_LEN:
            m["content"] = m["content"][:STUB_LEN] + " …[stubbed by compaction]"
            changed = True
    return changed


def _done(log, messages, before, applied):
    log.event(
        "compaction",
        mode="+".join(applied) or "none",
        tokens_before=before,
        tokens_after=estimate_tokens(messages),
    )
    return messages


def compact(messages, llm, log, budget=None):
    budget = budget or TOKEN_BUDGET
    before = estimate_tokens(messages)
    if before <= budget:
        return messages
    applied = []

    # Step 1: stub tool results outside the recent window.
    cutoff = max(1, len(messages) - KEEP_RECENT)
    if _stub_tools(messages[1:cutoff]):
        applied.append("stub-old-tools")
    if estimate_tokens(messages) <= budget:
        return _done(log, messages, before, applied)

    # Step 2: summarize the older part into one message.
    cut = _safe_cut(messages, cutoff)
    old, recent = messages[1:cut], messages[cut:]
    if old:
        summary_request = [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": json.dumps(old, ensure_ascii=False)[:100_000]},
        ]
        summary = llm.complete(summary_request)["content"] or ""
        messages = [
            messages[0],
            {"role": "user", "content": "[Conversation so far, compacted by the harness]\n" + summary},
        ] + recent
        applied.append("summarize")
        if estimate_tokens(messages) <= budget:
            return _done(log, messages, before, applied)

    # Step 3 (last resort): stub tool results inside the recent window too —
    # a single huge read can otherwise never be compacted.
    if _stub_tools(messages[1:]):
        applied.append("stub-recent-tools")
    return _done(log, messages, before, applied)
