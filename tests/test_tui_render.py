"""Tests for tui.render.render_blocks -- pure Block -> FormattedText
rendering. No terminal/Application needed; blocks are hand-built via
tui.blocks.Block directly."""

from make_harness.loop import DENIED_RESULT, SHORT_CIRCUIT_RESULT
from make_harness.tui.blocks import Block
from make_harness.tui.render import render_blocks


def _flatten_text(fragments):
    return "".join(text for _, text in fragments)


def _contains_text(fragments, text):
    """Check if rendered fragments contain the given text."""
    flat = _flatten_text(fragments)
    return text in flat


def test_user_block_format():
    block = Block(id="user-1", kind="user", text="hi there")
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert "YOU" in flat
    assert "hi there" in flat


def test_answer_block_format():
    block = Block(id="answer-1", kind="answer", text="42")
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert "AGENT" in flat
    assert "42" in flat


def test_collapsed_reasoning_pinned_format():
    block = Block(id="r1", kind="reasoning", text="x" * 412, collapsible=True, collapsed=True)
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert "THINKING" in flat
    assert "412 chars" in flat
    assert "~103t" in flat  # token estimate


def test_collapsed_reasoning_hides_the_full_text():
    text = "THE SECRET REASONING CONTENT " * 20
    block = Block(id="r1", kind="reasoning", text=text, collapsible=True, collapsed=True)
    out = render_blocks([block])
    assert "THE SECRET REASONING CONTENT" not in _flatten_text(out)


def test_expanded_reasoning_shows_the_full_text():
    block = Block(id="r1", kind="reasoning", text="line one\nline two", collapsible=True, collapsed=False)
    flat = _flatten_text(render_blocks([block]))
    assert "line one" in flat
    assert "line two" in flat


def test_expanded_reasoning_indents_each_natural_line():
    block = Block(id="r1", kind="reasoning", text="alpha\nbeta", collapsible=True, collapsed=False)
    flat = _flatten_text(render_blocks([block]))
    # Both lines should appear, indented under the header
    assert "alpha" in flat
    assert "beta" in flat


def test_tool_block_executed_uses_success_style():
    block = Block(id="c1", kind="tool", text="content of x.py", meta={"tool": "read_file", "args": '{"path": "x.py"}'})
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert "TOOL" in flat
    assert "read_file" in flat
    assert "content of x.py" in flat


def test_tool_block_denied_uses_denied_style():
    block = Block(id="c1", kind="tool", text=DENIED_RESULT, meta={"tool": "run_command", "args": "{}"})
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert "TOOL" in flat
    assert DENIED_RESULT in flat
    # Should have a denied-style outcome icon
    assert "⊘" in flat


def test_tool_block_short_circuit_uses_denied_style():
    block = Block(id="c1", kind="tool", text=SHORT_CIRCUIT_RESULT, meta={"tool": "probe", "args": "{}"})
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert SHORT_CIRCUIT_RESULT in flat
    assert "⊘" in flat


def test_tool_block_args_are_truncated():
    long_args = '{"path": "' + "x" * 300 + '"}'
    block = Block(id="c1", kind="tool", text="ok", meta={"tool": "read_file", "args": long_args})
    out = render_blocks([block])
    flat = _flatten_text(out)
    # Full args should not appear (they're truncated to ARGS_PREVIEW_CHARS=200)
    assert long_args not in flat
    assert "read_file" in flat


def test_focused_block_gets_focus_indicator():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block], focused_id="user-1")
    flat = _flatten_text(out)
    # Focused blocks have a bullet indicator
    assert "●" in flat


def test_unfocused_block_gets_no_focus_indicator():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block], focused_id="something-else")
    flat = _flatten_text(out)
    # Unfocused blocks have spacing instead
    assert flat.startswith("  ")


def test_no_focused_id_defaults_to_no_focus_indicator():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block])
    flat = _flatten_text(out)
    assert flat.startswith("  ")


def test_multiple_blocks_render_in_order():
    blocks = [
        Block(id="user-1", kind="user", text="hi"),
        Block(id="answer-1", kind="answer", text="hello"),
    ]
    out = render_blocks(blocks)
    flat = _flatten_text(out)
    assert "YOU" in flat
    assert "hi" in flat
    assert "AGENT" in flat
    assert "hello" in flat


def test_empty_blocks_list_renders_nothing():
    assert render_blocks([]) == []
