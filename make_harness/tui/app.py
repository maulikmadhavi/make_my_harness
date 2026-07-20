"""Full-screen Application: layout, scrolling, and fold/focus key
bindings over the render.py/blocks.py model.

Stage 19 wires this up against a static demo block list to prove the
layout, scrolling, and fold/focus interactions work before Stage 20
adds live threading and Stage 21 adds a real, editable input box.
run_demo() is a throwaway entry point for that purpose only — Stage 21
replaces it with the real live-turn-backed one. There is deliberately no
input box yet: with nothing else focusable, every key binding here can
stay global, avoiding the focus-scoping Stage 21 will need once a real
editable Buffer exists that must not have Up/Down/Space stolen from it
while typing.
"""

from prompt_toolkit import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.scroll import scroll_page_down, scroll_page_up
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from make_harness.tui.render import render_blocks

STYLE = Style.from_dict({
    "user": "bold fg:ansicyan",
    "answer": "bold fg:ansigreen",
    "dim": "fg:#888888",
    "yellow": "fg:ansiyellow",
})


class TranscriptState:
    """Holds the block list, per-block fold state, and which block (by
    index) is focused. Pure Python — no prompt_toolkit import — so it's
    directly unit-testable without a running Application."""

    def __init__(self, blocks=None, folds=None):
        self.blocks = blocks or []
        self.folds = folds if folds is not None else {}
        self.focused_index = len(self.blocks) - 1 if self.blocks else -1

    @property
    def focused_id(self):
        if 0 <= self.focused_index < len(self.blocks):
            return self.blocks[self.focused_index].id
        return None

    def move_focus(self, delta):
        if self.blocks:
            self.focused_index = max(0, min(len(self.blocks) - 1, self.focused_index + delta))

    def toggle_fold(self):
        if not self.blocks:
            return
        block = self.blocks[self.focused_index]
        if block.collapsible:
            block.collapsed = not block.collapsed
            self.folds[block.id] = block.collapsed

    def render(self):
        return render_blocks(self.blocks, focused_id=self.focused_id)

    def cursor_row(self):
        """Row index of the focused block's first rendered line, so the
        transcript Window auto-scrolls it into view when focus moves."""
        row = 0
        for block in self.blocks:
            if block.id == self.focused_id:
                return row
            row += sum(text.count("\n") for _, text in render_blocks([block]))
        return row


def build_application(state, input=None, output=None):
    """Build the Application. input/output are only ever passed
    explicitly by tests (prompt_toolkit's own headless testing utilities,
    create_pipe_input + DummyOutput) — the real CLI entry point (Stage 22)
    leaves both None so prompt_toolkit uses the real terminal."""
    control = FormattedTextControl(
        text=state.render,
        focusable=True,
        get_cursor_position=lambda: Point(x=0, y=state.cursor_row()),
    )
    transcript_window = Window(content=control, wrap_lines=True, always_hide_cursor=True)

    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event):
        state.move_focus(-1)

    @kb.add("down")
    def _move_down(event):
        state.move_focus(1)

    @kb.add("space")
    @kb.add("enter")
    def _fold(event):
        state.toggle_fold()

    kb.add("pageup")(scroll_page_up)
    kb.add("pagedown")(scroll_page_down)

    @kb.add("home")
    def _home(event):
        transcript_window.vertical_scroll = 0

    @kb.add("end")
    def _end(event):
        transcript_window.vertical_scroll = 10**9  # prompt_toolkit clamps to content height

    @kb.add("c-c")
    @kb.add("c-d")
    def _quit(event):
        event.app.exit()

    return Application(
        layout=Layout(transcript_window),
        key_bindings=kb,
        style=STYLE,
        full_screen=True,
        mouse_support=True,
        input=input,
        output=output,
    )


def _demo_blocks():
    from make_harness.tui.blocks import Block

    blocks = []
    for i in range(1, 9):
        blocks.append(Block(id=f"user-{i}", kind="user", text=f"Demo question number {i}?"))
        blocks.append(Block(
            id=f"reasoning-{i}", kind="reasoning",
            text=f"Reasoning for question {i}. " * 30,
            collapsible=True, collapsed=(i % 2 == 0),
        ))
        blocks.append(Block(id=f"answer-{i}", kind="answer", text=f"This is demo answer {i}."))
    return blocks


def run_demo():
    """Throwaway Stage 19 entry point: try scrolling (PageUp/PageDown/
    Home/End), moving focus (Up/Down), and folding (Space/Enter) in a
    real terminal, then quit with Ctrl+C. See make_harness/tui/app.py's
    module docstring — Stage 21 replaces this with the real entry point.
    """
    state = TranscriptState(blocks=_demo_blocks())
    build_application(state).run()


if __name__ == "__main__":
    run_demo()
