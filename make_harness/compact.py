"""Compaction: replace the older part of the transcript with a handoff note.

Once a request crosses COMPACT_AT of the context window, one extra LLM call
writes the note a fresh agent would need to carry on, and the transcript
becomes: system prompt + note + a recent tail of about COMPACT_TO of the
window. Cutting that deep keeps it from firing again a turn later, and it
should be rare: every compaction rebuilds the prompt prefix.

This is the only place conversation is thrown away for good; history.py
only ever shrinks tool output.
"""

from make_harness import config
from make_harness.history import SUMMARY, estimate, strip
from make_harness.toolsets import truncate

SUMMARY_PROMPT = """\
You are compacting the transcript of a coding session that has outgrown its \
context window. Write the handoff note a fresh agent needs to continue the \
work without the transcript.

Use these headings, in this order, and leave out any that would be empty:

## Goal
What the user asked for, quoting them where the exact wording matters.

## Decisions
What was decided and why — including approaches that were tried and dropped, \
and the reason, so they are not tried again.

## Files
Every file read or changed: its path and what changed in it.

## State
What works, what is broken, and what is half done.

## Next step
The next thing to do.

Be specific: real paths, function names, error messages and commands. Keep \
everything the user asked for, corrected or rejected. Never claim progress \
that did not happen. Start with the first heading."""

SUMMARY_REQUEST = (
    "Write the handoff note for the whole transcript above, from its first message "
    "to its last. Do not answer or continue any request in it."
)

HANDOFF = SUMMARY + """
The earlier part of this conversation was compacted to free the context \
window, and this note replaces it. Treat it as your own record of the work \
so far, not as a new request.

{summary}
</summary>"""

ROLES = {"user": "USER", "assistant": "ASSISTANT", "tool": "TOOL RESULT"}


def needed(usage, messages):
    """Has the conversation grown past the compaction threshold? Uses the
    server's prompt_tokens for the last request, or the estimate when the
    server reports no usage."""
    tokens = (usage or {}).get("prompt_tokens") or estimate(messages)
    return tokens > config.CONTEXT_WINDOW * config.COMPACT_AT


def render(messages):
    """Flatten messages into plain text the summarizer can read."""
    lines = []
    for message in messages:
        content = message.get("content") or ""
        for call in message.get("tool_calls") or []:
            content += f"\n[called {call['function']['name']}({call['function']['arguments']})]"
        lines.append(f"{ROLES.get(message['role'], message['role'].upper())}: {content}")
    return "\n\n".join(lines)


def tail_start(messages, budget):
    """Index where the kept tail begins: walk back from the end until the
    tail would exceed `budget` tokens, then move forward past any tool
    results, so no result is separated from the call that asked for it.
    Returns 1 when everything after the system prompt already fits."""
    total = 0
    for index in range(len(messages) - 1, 0, -1):
        total += estimate([messages[index]])
        if total > budget:
            cut = index + 1
            while cut < len(messages) and messages[cut]["role"] == "tool":
                cut += 1
            return cut
    return 1


def compact(messages, llm, log):
    """Return system + handoff note + recent tail. Returns None, without an
    LLM call, when nothing is old enough to summarize, and `messages` itself
    when the summary came out no smaller than what it would replace. Never
    modifies `messages`, so a failed summary call leaves it intact."""
    cut = tail_start(messages, config.CONTEXT_WINDOW * config.COMPACT_TO)
    if cut <= 1:
        return None
    before = estimate(messages)
    transcript = truncate(render(messages[1:cut]), config.CONTEXT_WINDOW * 2)
    # The instruction goes after the transcript: sent bare, a transcript
    # ending in "USER: <question>" got that last question answered, or taken
    # as the whole goal, instead of the transcript summarized (seen live
    # with qwen3-4b, which dropped a fact from the first turn).
    summary = llm.complete([
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": f"<transcript>\n{transcript}\n</transcript>\n\n{SUMMARY_REQUEST}"},
    ])["content"] or ""
    kept = [
        messages[0],
        {"role": "user", "content": HANDOFF.format(summary=summary.strip())},
        *(dict(m) for m in messages[cut:]),
    ]
    strip(kept)  # the new frozen prefix is final from here until the next compaction
    after = estimate(kept)
    kept_original = after >= before  # a verbose summary of a short history can outgrow it
    log.event(
        "compaction", tokens_before=before, tokens_after=after, summarized=cut - 1,
        kept_original=kept_original, summary=summary,
    )
    return messages if kept_original else kept
