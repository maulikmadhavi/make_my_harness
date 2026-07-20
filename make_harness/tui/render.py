"""Pure rendering: Block objects -> prompt_toolkit FormattedText.

No Application/Layout import here, only the formatted_text types -- just
style-tagged text fragments. Terminal-width wrapping of long lines is
left to the eventual Window's wrap_lines=True (Stage 19); this module
only emits real line breaks (block boundaries, the reasoning
header/body split, a text's own embedded newlines).
"""

from prompt_toolkit.formatted_text import FormattedText

from make_harness.loop import DENIED_RESULT, SHORT_CIRCUIT_RESULT

FOCUS_MARKER = "> "
NO_MARKER = "  "
ARGS_PREVIEW_CHARS = 200


def _estimate_tokens(text):
    """Same chars//4 heuristic context.py uses for its own token budget
    math, inlined here to keep tui/ decoupled from context.py."""
    return len(text) // 4


def _gutter(block, focused_id):
    return FOCUS_MARKER if block.id == focused_id else NO_MARKER


def _render_user(block, focused_id):
    return [("class:user", f"{_gutter(block, focused_id)}you > {block.text}\n")]


def _render_answer(block, focused_id):
    return [("class:answer", f"{_gutter(block, focused_id)}agent > {block.text}\n")]


def _render_reasoning(block, focused_id):
    gutter = _gutter(block, focused_id)
    if block.collapsed:
        tokens = _estimate_tokens(block.text)
        return [("class:dim", f"{gutter}▸ thinking ({len(block.text)} chars, ~{tokens} tokens)\n")]
    fragments = [("class:dim", f"{gutter}▾ thinking ({len(block.text)} chars)\n")]
    for line in block.text.splitlines() or [""]:
        fragments.append(("class:dim", f"    {line}\n"))
    return fragments


def _render_tool(block, focused_id):
    gutter = _gutter(block, focused_id)
    name = block.meta.get("tool", "?")
    args = block.meta.get("args", "")[:ARGS_PREVIEW_CHARS]
    outcome_style = "class:yellow" if block.text in (DENIED_RESULT, SHORT_CIRCUIT_RESULT) else "class:dim"
    return [
        ("class:dim", f"{gutter}→ {name}({args})\n"),
        (outcome_style, f"  ← {block.text}\n"),
    ]


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
