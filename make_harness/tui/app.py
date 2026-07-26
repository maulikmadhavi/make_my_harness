"""Full-screen Application: layout, scrolling, and fold/focus key
bindings over the render.py/blocks.py model.

Stage 19-20: Static demo with scrolling and fold/focus.
Stage 21: Adds editable input buffer at the bottom.
Stage 22: Integrates with live agent loop.
"""

from prompt_toolkit import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.scroll import scroll_page_down, scroll_page_up
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.containers import HSplit, VSplit
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.styles import Style

from make_harness.tui.render import render_blocks

STYLE = Style.from_dict({
    # Block headers
    "user.header": "bold fg:#00d084 bg:#0a0e27",
    "answer.header": "bold fg:#10b981 bg:#0a0e27",
    "reasoning.header": "bold fg:#64748b bg:#0a0e27",
    "tool.header": "bold fg:#06b6d4 bg:#0a0e27",

    # Block content
    "user": "fg:#e0e7ff",
    "answer": "fg:#ecfdf5",
    "reasoning": "fg:#94a3b8",
    "tool": "fg:#cffafe",

    # Tool outcomes
    "tool.success": "fg:#10b981 bold",
    "tool.error": "fg:#ef4444 bold",
    "tool.denied": "fg:#fbbf24 bold",
    "tool.pending": "fg:#fbbf24",

    # Separators & focus
    "border": "fg:#334155",
    "focus": "fg:#00d084",
    "focus.bg": "bg:#1e293b",

    # Metadata
    "meta": "fg:#475569",
    "meta.bold": "bold fg:#64748b",
    "token.count": "fg:#94a3b8",

    # Status
    "status": "fg:#64748b bg:#0f172a",
    "status.active": "bold fg:#00d084 bg:#0f172a",
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


def build_application(state, input_buffer=None, input=None, output=None, on_submit=None):
    """Build the Application with editable input buffer (Stage 21).

    Args:
        state: TranscriptState holding blocks and fold state
        input_buffer: Optional Buffer for user input (Stage 21+). If None, no input box.
        input/output: TTY I/O for tests (create_pipe_input + DummyOutput)
        on_submit: Optional callback(text) when user submits input
    """

    # Create input buffer if not provided (Stage 21)
    if input_buffer is None:
        def on_input_accept(_):
            """Handle Enter key in input buffer."""
            text = input_buffer.text.strip()
            if text and on_submit:
                on_submit(text)
                input_buffer.text = ""

        input_buffer = Buffer(multiline=False, completer=None, accept_handler=on_input_accept)

    # Header bar
    header_text = FormattedTextControl(
        lambda: [
            ("class:status.active", "make_harness"),
            ("class:status", " v0.1.0 • "),
            ("class:status", "⬆↓ navigate  Space/Enter fold (transcript)  Enter submit (input)  Ctrl+C quit"),
        ]
    )
    header_window = Window(content=header_text, height=1, style="class:status")

    # Transcript (main area, focusable for navigation)
    transcript_control = FormattedTextControl(
        text=state.render,
        focusable=True,
        get_cursor_position=lambda: Point(x=0, y=state.cursor_row()),
    )
    transcript_window = Window(content=transcript_control, wrap_lines=True, always_hide_cursor=True)

    # Input box (Stage 21) - focused by default
    input_control = BufferControl(
        buffer=input_buffer,
        input_processors=[],
        focus_on_click=True,
        search_buffer_control=None,
    )
    input_window = Window(
        content=input_control,
        height=1,
        style="class:user",
        wrap_lines=False,
        always_hide_cursor=False,  # Show cursor in input box
    )

    # Input prompt
    prompt_text = FormattedTextControl(
        lambda: [
            ("class:user.header", "▶ YOU"),
            ("class:border", "\n"),
        ]
    )
    prompt_window = Window(content=prompt_text, height=2, style="class:status")

    # Footer bar
    footer_text = FormattedTextControl(
        lambda: [
            ("class:status", "Focused: "),
            ("class:status.active", state.focused_id or "—"),
            ("class:status", f" • Blocks: {len(state.blocks)}"),
        ]
    )
    footer_window = Window(content=footer_text, height=1, style="class:status")

    kb = KeyBindings()

    # Filters for key bindings: only apply to transcript when input is empty
    def input_is_empty():
        return input_buffer.text.strip() == ""

    @kb.add("up", filter=Condition(input_is_empty))
    def _move_up(event):
        state.move_focus(-1)

    @kb.add("down", filter=Condition(input_is_empty))
    def _move_down(event):
        state.move_focus(1)

    @kb.add("space", filter=Condition(input_is_empty))
    def _fold_space(event):
        state.toggle_fold()

    @kb.add("pageup", filter=Condition(input_is_empty))
    def _pageup(event):
        scroll_page_up(event)

    @kb.add("pagedown", filter=Condition(input_is_empty))
    def _pagedown(event):
        scroll_page_down(event)

    @kb.add("home", filter=Condition(input_is_empty))
    def _home(event):
        transcript_window.vertical_scroll = 0

    @kb.add("end", filter=Condition(input_is_empty))
    def _end(event):
        transcript_window.vertical_scroll = 10**9

    # Escape clears input
    @kb.add("escape")
    def _clear_input(event):
        if input_buffer.text:
            input_buffer.text = ""
        else:
            event.app.exit()

    @kb.add("c-c")
    @kb.add("c-d")
    def _quit(event):
        event.app.exit()

    return Application(
        layout=Layout(HSplit([
            header_window,
            transcript_window,
            prompt_window,
            input_window,
            footer_window,
        ])),
        key_bindings=kb,
        style=STYLE,
        full_screen=True,
        mouse_support=True,
        enable_page_navigation_bindings=True,
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
    """Demo with interactive input (Stage 21).

    Try:
    - Click input box and type, press Enter to submit
    - Escape to clear input
    - Up/Down: move focus between blocks (when input is empty)
    - Space/Enter: collapse/expand reasoning (when input is empty)
    - PgUp/PgDn: scroll (when input is empty)
    - Ctrl+C: quit
    """
    state = TranscriptState(blocks=_demo_blocks())

    def on_demo_submit(text):
        """Echo user input as a demo."""
        from make_harness.tui.blocks import Block
        state.blocks.append(Block(id=f"user-demo-{len(state.blocks)}", kind="user", text=text))
        state.blocks.append(Block(id=f"answer-demo-{len(state.blocks)}", kind="answer", text=f"You said: {text}"))
        state.focused_index = len(state.blocks) - 1

    build_application(state, on_submit=on_demo_submit).run()


if __name__ == "__main__":
    run_demo()
