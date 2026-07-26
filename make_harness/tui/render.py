"""Pure rendering: Block objects -> prompt_toolkit FormattedText.

No Application/Layout import here, only the formatted_text types -- just
style-tagged text fragments. Terminal-width wrapping of long lines is
left to the eventual Window's wrap_lines=True (Stage 19); this module
only emits real line breaks (block boundaries, the reasoning
header/body split, a text's own embedded newlines).
"""

from prompt_toolkit.formatted_text import FormattedText

from make_harness.loop import DENIED_RESULT, SHORT_CIRCUIT_RESULT

ARGS_PREVIEW_CHARS = 200


def _estimate_tokens(text):
    """Same chars//4 heuristic context.py uses for its own token budget
    math, inlined here to keep tui/ decoupled from context.py."""
    return len(text) // 4


def _focus_indicator(block, focused_id):
    """Visual indicator for focused vs unfocused state."""
    if block.id == focused_id:
        return ("class:focus", "● ")
    return ("class:border", "  ")


def _render_user(block, focused_id):
    """User message with professional formatting."""
    indicator = _focus_indicator(block, focused_id)
    fragments = []

    # Header with icon
    fragments.append(indicator)
    fragments.append(("class:user.header", "▶ YOU"))
    fragments.append(("class:border", "\n"))

    # Content with left padding
    for line in block.text.splitlines() or [""]:
        fragments.append(("class:border", "  "))
        fragments.append(("class:user", line))
        fragments.append(("class:border", "\n"))

    # Separator
    fragments.append(("class:border", "\n"))
    return fragments


def _render_answer(block, focused_id):
    """Agent response with professional formatting."""
    indicator = _focus_indicator(block, focused_id)
    fragments = []

    # Header with icon
    fragments.append(indicator)
    fragments.append(("class:answer.header", "◆ AGENT"))
    fragments.append(("class:border", "\n"))

    # Content with left padding
    for line in block.text.splitlines() or [""]:
        fragments.append(("class:border", "  "))
        fragments.append(("class:answer", line))
        fragments.append(("class:border", "\n"))

    # Separator
    fragments.append(("class:border", "\n"))
    return fragments


def _render_reasoning(block, focused_id):
    """Reasoning/thinking block with collapse UI."""
    indicator = _focus_indicator(block, focused_id)
    fragments = []

    # Header with collapse indicator
    fragments.append(indicator)
    collapse_char = "▸" if block.collapsed else "▾"
    fragments.append(("class:reasoning.header", f"{collapse_char} THINKING"))

    # Metadata on same line as header
    tokens = _estimate_tokens(block.text)
    fragments.append(("class:meta", f" ({len(block.text)} chars, ~{tokens}t)"))
    fragments.append(("class:border", "\n"))

    # Content (if expanded)
    if not block.collapsed:
        for line in block.text.splitlines() or [""]:
            fragments.append(("class:border", "  "))
            fragments.append(("class:reasoning", line))
            fragments.append(("class:border", "\n"))

    # Separator
    fragments.append(("class:border", "\n"))
    return fragments


def _render_tool(block, focused_id):
    """Tool call with outcome indicator."""
    indicator = _focus_indicator(block, focused_id)
    fragments = []

    name = block.meta.get("tool", "?")
    args = block.meta.get("args", "")[:ARGS_PREVIEW_CHARS]
    result = block.text

    # Determine outcome style and icon
    if result in (DENIED_RESULT, SHORT_CIRCUIT_RESULT):
        outcome_style = "class:tool.denied"
        outcome_icon = "⊘"
    elif result.startswith("Error") or result.startswith("error"):
        outcome_style = "class:tool.error"
        outcome_icon = "✗"
    elif result:
        outcome_style = "class:tool.success"
        outcome_icon = "✓"
    else:
        outcome_style = "class:tool.pending"
        outcome_icon = "⧗"

    # Tool call header
    fragments.append(indicator)
    fragments.append(("class:tool.header", "→ TOOL"))
    fragments.append(("class:border", " "))
    fragments.append(("class:tool", name))
    fragments.append(("class:meta", f"({args})"))
    fragments.append(("class:border", "\n"))

    # Result line with outcome indicator
    fragments.append(("class:border", "  "))
    fragments.append((outcome_style, f"{outcome_icon} "))
    fragments.append((outcome_style, result if result else "pending…"))
    fragments.append(("class:border", "\n"))

    # Separator
    fragments.append(("class:border", "\n"))
    return fragments


_RENDERERS = {
    "user": _render_user,
    "reasoning": _render_reasoning,
    "tool": _render_tool,
    "answer": _render_answer,
}


def render_blocks(blocks, focused_id=None):
    """Render a Block list to FormattedText -- one call per full
    transcript render (the block model is re-derived and re-rendered
    from scratch on every update; see blocks.py's own note on this)."""
    fragments = []
    for block in blocks:
        fragments.extend(_RENDERERS[block.kind](block, focused_id))
    return FormattedText(fragments)
