"""Tests for tui.blocks.build_blocks -- the pure transcript-to-blocks
data model. Message-list fixtures are hand-built OpenAI-format dicts,
the same convention tests/test_context.py already uses for this shape.
"""

from make_harness.loop import SHORT_CIRCUIT_RESULT
from make_harness.tui.blocks import build_blocks


def _msg(role, content, **extra):
    return {"role": role, "content": content, **extra}


def _tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def test_plain_qa_produces_a_reasoning_and_answer_block():
    messages = [
        _msg("system", "sys"),
        _msg("user", "what is 2+2?"),
        _msg("assistant", "4"),
    ]
    blocks = build_blocks(messages, ["it's basic arithmetic, 4"], {})
    assert [b.kind for b in blocks] == ["user", "reasoning", "answer"]
    assert blocks[0].text == "what is 2+2?"
    assert blocks[1].text == "it's basic arithmetic, 4"
    assert blocks[1].collapsible is True
    assert blocks[2].text == "4"
    assert blocks[2].collapsible is False


def test_tool_call_produces_reasoning_and_tool_blocks():
    messages = [
        _msg("system", "sys"),
        _msg("user", "read x.py"),
        _msg("assistant", None, tool_calls=[_tool_call("c1", "read_file", '{"path": "x.py"}')]),
        _msg("tool", "print(1)", tool_call_id="c1"),
        _msg("assistant", "it prints 1"),
    ]
    blocks = build_blocks(messages, ["need to read the file", "now I can answer"], {})
    assert [b.kind for b in blocks] == ["user", "reasoning", "tool", "reasoning", "answer"]
    tool_block = blocks[2]
    assert tool_block.id == "c1"
    assert tool_block.text == "print(1)"
    assert tool_block.meta == {"tool": "read_file", "args": '{"path": "x.py"}'}
    assert tool_block.collapsible is False


def test_denied_tool_call_text_comes_through_as_is():
    messages = [
        _msg("system", "sys"),
        _msg("user", "delete everything"),
        _msg("assistant", None, tool_calls=[_tool_call("c1", "run_command", '{"command": "rm -rf /"}')]),
        _msg("tool", "Denied by user.", tool_call_id="c1"),
    ]
    blocks = build_blocks(messages, [None], {})
    tool_block = next(b for b in blocks if b.kind == "tool")
    assert tool_block.text == "Denied by user."


def test_short_circuit_result_text_comes_through_as_is():
    messages = [
        _msg("system", "sys"),
        _msg("user", "go"),
        _msg("assistant", None, tool_calls=[_tool_call("c2", "probe", "{}")]),
        _msg("tool", SHORT_CIRCUIT_RESULT, tool_call_id="c2"),
    ]
    blocks = build_blocks(messages, [None], {})
    tool_block = next(b for b in blocks if b.kind == "tool")
    assert tool_block.text == SHORT_CIRCUIT_RESULT


def test_multiple_tool_calls_in_one_batch_each_get_a_block():
    messages = [
        _msg("system", "sys"),
        _msg("user", "check both files"),
        _msg("assistant", None, tool_calls=[
            _tool_call("c1", "read_file", '{"path": "a.py"}'),
            _tool_call("c2", "read_file", '{"path": "b.py"}'),
        ]),
        _msg("tool", "content a", tool_call_id="c1"),
        _msg("tool", "content b", tool_call_id="c2"),
    ]
    tool_blocks = [b for b in build_blocks(messages, [None], {}) if b.kind == "tool"]
    assert [b.id for b in tool_blocks] == ["c1", "c2"]
    assert [b.text for b in tool_blocks] == ["content a", "content b"]


def test_empty_or_missing_reasoning_produces_no_reasoning_block():
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "hello")]
    for reasoning_events in ([None], [""], []):
        blocks = build_blocks(messages, reasoning_events, {})
        assert [b.kind for b in blocks] == ["user", "answer"]


def test_reasoning_events_align_positionally_across_multiple_assistant_steps():
    # Step 0 has no reasoning, step 1 does -- the missing entry at index 0
    # must not shift step 1's reasoning onto the wrong assistant message.
    messages = [
        _msg("system", "sys"),
        _msg("user", "go"),
        _msg("assistant", None, tool_calls=[_tool_call("c1", "probe", "{}")]),
        _msg("tool", "ok", tool_call_id="c1"),
        _msg("assistant", "done"),
    ]
    blocks = build_blocks(messages, [None, "now I'm ready to answer"], {})
    assert [b.kind for b in blocks] == ["user", "tool", "reasoning", "answer"]
    assert blocks[2].text == "now I'm ready to answer"


def test_system_message_is_skipped():
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "hello")]
    blocks = build_blocks(messages, [None], {})
    assert all(b.kind != "system" for b in blocks)
    assert len(blocks) == 2


def test_fold_threshold_default_collapses_long_reasoning():
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "ok")]
    blocks = build_blocks(messages, ["x" * 500], {})
    assert next(b for b in blocks if b.kind == "reasoning").collapsed is True


def test_fold_threshold_default_expands_short_reasoning():
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "ok")]
    blocks = build_blocks(messages, ["x" * 50], {})
    assert next(b for b in blocks if b.kind == "reasoning").collapsed is False


def test_fold_threshold_env_override(monkeypatch):
    monkeypatch.setenv("HARNESS_REASONING_FOLD_CHARS", "10")
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "ok")]
    blocks = build_blocks(messages, ["x" * 50], {})
    assert next(b for b in blocks if b.kind == "reasoning").collapsed is True  # 50 > 10


def test_fold_state_survives_across_growing_calls():
    # Simulates a live turn: build_blocks is called again as more messages
    # arrive, with the same folds dict passed both times.
    base = [_msg("system", "sys"), _msg("user", "hi")]
    folds = {}
    long_reasoning = "x" * 500

    step1_messages = base + [_msg("assistant", None, tool_calls=[_tool_call("c1", "probe", "{}")])]
    blocks1 = build_blocks(step1_messages, [long_reasoning], folds)
    reasoning_id = next(b.id for b in blocks1 if b.kind == "reasoning")
    assert folds[reasoning_id] is True  # auto-collapsed, long text

    # User manually expands it (what the TUI's fold key binding will do).
    folds[reasoning_id] = False

    step2_messages = step1_messages + [_msg("tool", "ok", tool_call_id="c1"), _msg("assistant", "done")]
    blocks2 = build_blocks(step2_messages, [long_reasoning, None], folds)
    assert next(b for b in blocks2 if b.id == reasoning_id).collapsed is False  # override survived


def test_block_ids_are_stable_across_repeated_calls():
    messages = [_msg("system", "sys"), _msg("user", "hi"), _msg("assistant", "hello")]
    ids1 = [b.id for b in build_blocks(messages, [None], {})]
    ids2 = [b.id for b in build_blocks(messages, [None], {})]
    assert ids1 == ids2
