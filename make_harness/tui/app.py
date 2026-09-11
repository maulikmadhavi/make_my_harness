"""Full-screen Application: layout, scrolling, fold/focus key bindings
and the input box, over the render.py/blocks.py model. Wired to the
live agent loop by make_harness/cli.py::run_tui_repl.
"""

from prompt_toolkit import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.scroll import scroll_page_down, scroll_page_up
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.styles import Style

from make_harness import __version__
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

    # Metadata
    "meta": "fg:#475569",

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


def build_application(state, input=None, output=None, on_submit=None):
    """Build the full-screen Application: header, transcript, input box, footer.

    Args:
        state: TranscriptState holding blocks and fold state
        input/output: TTY I/O for tests (create_pipe_input + DummyOutput)
        on_submit: callback(text) for each non-empty submitted line
    """

    def on_input_accept(_):
        """Enter in the input box: hand the line to on_submit, then clear."""
        text = input_buffer.text.strip()
        if text and on_submit:
            on_submit(text)
            input_buffer.text = ""

    input_buffer = Buffer(multiline=False, accept_handler=on_input_accept)

    # Header bar
    header_text = FormattedTextControl(
        lambda: [
            ("class:status.active", "make_harness"),
            ("class:status", f" v{__version__} • "),
            ("class:status", "↑↓ navigate  Space fold  PgUp/PgDn scroll  Enter submit  Esc clear/quit  Ctrl+C quit"),
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

    # Input box (focused by default)
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
