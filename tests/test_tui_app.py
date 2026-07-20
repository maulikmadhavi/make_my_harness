"""Tests for tui.app.

TranscriptState is pure Python and unit-tested directly, no terminal
needed (same style test_prompt.py uses for get_completions()). One
integration test drives a real Application headlessly via
prompt_toolkit's own testing utilities (create_pipe_input + DummyOutput
-- the same pattern prompt_toolkit's and IPython's test suites use),
confirming the whole layout/key-binding wiring runs without crashing and
actually mutates state on real (simulated) keypresses. True visual
behavior (does PageDown look right, does auto-scroll-to-focus track
correctly on screen) can't be verified without a real terminal -- that's
a live-smoke, not a CI, concern (see plan.md's Stage 19 entry).
"""

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from make_harness.tui.app import TranscriptState, build_application
from make_harness.tui.blocks import Block

# Exact VT100 escape sequences prompt_toolkit's input parser maps to each
# key binding name -- verified against the installed prompt_toolkit by
# actually firing each one and checking which handler ran.
KEY = {
    "up": "\x1b[A",
    "down": "\x1b[B",
    "space": " ",
    "enter": "\r",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "ctrl-c": "\x03",
}


def _blocks():
    return [
        Block(id="user-1", kind="user", text="hi"),
        Block(id="reasoning-1", kind="reasoning", text="thinking...", collapsible=True, collapsed=True),
        Block(id="answer-1", kind="answer", text="hello"),
    ]


def test_new_state_focuses_the_last_block():
    state = TranscriptState(blocks=_blocks())
    assert state.focused_index == 2
    assert state.focused_id == "answer-1"


def test_empty_state_has_no_focus():
    state = TranscriptState()
    assert state.focused_index == -1
    assert state.focused_id is None


def test_move_focus_clamps_at_both_ends():
    state = TranscriptState(blocks=_blocks())
    state.move_focus(-10)
    assert state.focused_index == 0
    state.move_focus(10)
    assert state.focused_index == 2


def test_move_focus_on_empty_state_does_not_crash():
    state = TranscriptState()
    state.move_focus(1)
    assert state.focused_index == -1


def test_toggle_fold_flips_a_collapsible_block():
    state = TranscriptState(blocks=_blocks())
    state.focused_index = 1  # the reasoning block, starts collapsed
    state.toggle_fold()
    assert state.blocks[1].collapsed is False
    assert state.folds["reasoning-1"] is False
    state.toggle_fold()
    assert state.blocks[1].collapsed is True
    assert state.folds["reasoning-1"] is True


def test_toggle_fold_on_a_non_collapsible_block_is_a_no_op():
    state = TranscriptState(blocks=_blocks())
    state.focused_index = 2  # the answer block
    state.toggle_fold()
    assert state.blocks[2].collapsed is False
    assert "answer-1" not in state.folds


def test_toggle_fold_on_empty_state_does_not_crash():
    TranscriptState().toggle_fold()


def test_render_passes_through_the_focused_id():
    state = TranscriptState(blocks=_blocks())
    state.focused_index = 0
    out = state.render()
    assert out[0][1].startswith("> ")  # user-1, focused
    assert out[-1][1].startswith("  ")  # answer-1, not focused


def test_cursor_row_accounts_for_preceding_block_heights():
    state = TranscriptState(blocks=_blocks())
    state.focused_index = 0
    assert state.cursor_row() == 0  # first block, first line
    state.focused_index = 2
    # user-1 (1 line, collapsed reasoning-1 (1 line) precede answer-1
    assert state.cursor_row() == 2


def test_cursor_row_on_empty_state_is_zero():
    assert TranscriptState().cursor_row() == 0


def test_headless_app_runs_and_key_bindings_mutate_state():
    state = TranscriptState(blocks=_blocks())
    assert state.focused_index == 2  # starts on answer-1

    with create_pipe_input() as pipe_input:
        app = build_application(state, input=pipe_input, output=DummyOutput())
        pipe_input.send_text(KEY["up"])  # -> reasoning-1
        pipe_input.send_text(KEY["up"])  # -> user-1
        pipe_input.send_text(KEY["down"])  # -> reasoning-1
        pipe_input.send_text(KEY["space"])  # unfold it
        pipe_input.send_text(KEY["pagedown"])
        pipe_input.send_text(KEY["pageup"])
        pipe_input.send_text(KEY["home"])
        pipe_input.send_text(KEY["end"])
        pipe_input.send_text(KEY["ctrl-c"])
        app.run()

    assert state.focused_index == 1  # ended on reasoning-1
    assert state.blocks[1].collapsed is False  # space unfolded it
    assert state.folds["reasoning-1"] is False


def test_headless_app_exits_cleanly_on_ctrl_d():
    state = TranscriptState(blocks=_blocks())
    with create_pipe_input() as pipe_input:
        app = build_application(state, input=pipe_input, output=DummyOutput())
        pipe_input.send_text("\x04")  # Ctrl-D
        app.run()  # must return, not hang or raise
