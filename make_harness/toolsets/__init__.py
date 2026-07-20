"""Shared helpers for tool implementations."""


def truncate(text, limit):
    """Cap text at limit chars keeping both the head and the tail.

    Head-only truncation is backwards for shell/build output, where the
    actual error is usually at the very end.
    """
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return (
        text[:head]
        + f"\n[... {len(text) - limit} chars truncated ...]\n"
        + text[-tail:]
    )
