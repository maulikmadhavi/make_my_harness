"""Tests for tui.render.render_blocks -- pure Block -> FormattedText
rendering. No terminal/Application needed; blocks are hand-built via
tui.blocks.Block directly."""

from make_harness.loop import DENIED_RESULT, SHORT_CIRCUIT_RESULT
from make_harness.tui.blocks import Block
from make_harness.tui.render import render_blocks


def _flatten_text(fragments):
    return "".join(text for _, text in fragments)


def test_user_block_format():
    block = Block(id="user-1", kind="user", text="hi there")
    out = render_blocks([block])
    assert out == [("class:user", "  you > hi there\n")]


def test_answer_block_format():
    block = Block(id="answer-1", kind="answer", text="42")
    out = render_blocks([block])
    assert out == [("class:answer", "  agent > 42\n")]


def test_collapsed_reasoning_pinned_format():
    block = Block(id="r1", kind="reasoning", text="x" * 412, collapsible=True, collapsed=True)
    out = render_blocks([block])
    assert out == [("class:dim", "  ▸ thinking (412 chars, ~103 tokens)\n")]


def test_collapsed_reasoning_hides_the_full_text():
    text = "THE SECRET REASONING CONTENT " * 20
    block = Block(id="r1", kind="reasoning", text=text, collapsible=True, collapsed=True)
    out = render_blocks([block])
    assert "THE SECRET REASONING CONTENT" not in _flatten_text(out)


def test_expanded_reasoning_pinned_header_and_body():
    block = Block(id="r1", kind="reasoning", text="a short thought", collapsible=True, collapsed=False)
    out = render_blocks([block])
    assert out[0] == ("class:dim", "  ▾ thinking (15 chars)\n")
    assert out[1] == ("class:dim", "    a short thought\n")


def test_expanded_reasoning_shows_the_full_text():
    block = Block(id="r1", kind="reasoning", text="line one\nline two", collapsible=True, collapsed=False)
    flat = _flatten_text(render_blocks([block]))
    assert "line one" in flat
    assert "line two" in flat


def test_expanded_reasoning_indents_each_natural_line():
    block = Block(id="r1", kind="reasoning", text="alpha\nbeta", collapsible=True, collapsed=False)
    out = render_blocks([block])
    assert [text for _, text in out[1:]] == ["    alpha\n", "    beta\n"]


def test_tool_block_executed_uses_dim_style():
    block = Block(id="c1", kind="tool", text="content of x.py", meta={"tool": "read_file", "args": '{"path": "x.py"}'})
    out = render_blocks([block])
    assert out[0] == ("class:dim", '  → read_file({"path": "x.py"})\n')
    assert out[1] == ("class:dim", "  ← content of x.py\n")


def test_tool_block_denied_uses_yellow_style():
    block = Block(id="c1", kind="tool", text=DENIED_RESULT, meta={"tool": "run_command", "args": "{}"})
    out = render_blocks([block])
    assert out[1] == ("class:yellow", f"  ← {DENIED_RESULT}\n")


def test_tool_block_short_circuit_uses_yellow_style():
    block = Block(id="c1", kind="tool", text=SHORT_CIRCUIT_RESULT, meta={"tool": "probe", "args": "{}"})
    out = render_blocks([block])
    assert out[1] == ("class:yellow", f"  ← {SHORT_CIRCUIT_RESULT}\n")


def test_tool_block_args_are_truncated():
    long_args = '{"path": "' + "x" * 300 + '"}'
    block = Block(id="c1", kind="tool", text="ok", meta={"tool": "read_file", "args": long_args})
    header = render_blocks([block])[0][1]
    assert len(header) < len(long_args)
    assert header.startswith("  → read_file(")


def test_focused_block_gets_the_gutter_marker():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block], focused_id="user-1")
    assert out[0][1].startswith("> ")


def test_unfocused_block_gets_no_gutter_marker():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block], focused_id="something-else")
    assert out[0][1].startswith("  ")


def test_no_focused_id_defaults_to_no_marker():
    block = Block(id="user-1", kind="user", text="hi")
    out = render_blocks([block])
    assert out[0][1].startswith("  ")


def test_multiple_blocks_render_in_order():
    blocks = [
        Block(id="user-1", kind="user", text="hi"),
        Block(id="answer-1", kind="answer", text="hello"),
    ]
    out = render_blocks(blocks)
    assert len(out) == 2
    assert "you > hi" in out[0][1]
    assert "agent > hello" in out[1][1]


def test_empty_blocks_list_renders_nothing():
    assert render_blocks([]) == []
