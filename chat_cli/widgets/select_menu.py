"""Arrow-key navigable selection menu."""
from __future__ import annotations

from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class SelectMenu(Widget, can_focus=True):
    """A vertical list of options navigable with Up/Down (or j/k) and confirmed with Enter."""

    DEFAULT_CSS = """
    SelectMenu {
        border: round $secondary;
        padding: 0 1;
        height: auto;
        width: auto;
    }
    SelectMenu > .option {
        padding: 0 2;
    }
    SelectMenu > .option--highlighted {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    """

    class Selected(Message):
        """Posted when the user confirms an option with Enter."""

        def __init__(self, menu: "SelectMenu", index: int, value: str) -> None:
            self.menu = menu
            self.index = index
            self.value = value
            super().__init__()

    class Cancelled(Message):
        """Posted when the user backs out of the menu with Escape."""

        def __init__(self, menu: "SelectMenu") -> None:
            self.menu = menu
            super().__init__()

    highlighted: reactive[int] = reactive(0)

    def __init__(self, options: list[str], *, title: str | None = None, id: str | None = None) -> None:
        if not options:
            raise ValueError("SelectMenu requires at least one option")
        super().__init__(id=id)
        self.options = options
        if title:
            self.border_title = title

    def compose(self):
        for index, option in enumerate(self.options):
            yield Static(option, classes="option", id=f"option-{index}")

    def on_mount(self) -> None:
        self._refresh_highlight()

    def watch_highlighted(self, old_index: int, new_index: int) -> None:
        self._refresh_highlight()

    def _refresh_highlight(self) -> None:
        for index in range(len(self.options)):
            node = self.query_one(f"#option-{index}", Static)
            node.set_class(index == self.highlighted, "option--highlighted")

    def on_key(self, event: events.Key) -> None:
        if event.key in ("up", "k"):
            self.highlighted = (self.highlighted - 1) % len(self.options)
            event.stop()
        elif event.key in ("down", "j"):
            self.highlighted = (self.highlighted + 1) % len(self.options)
            event.stop()
        elif event.key == "home":
            self.highlighted = 0
            event.stop()
        elif event.key == "end":
            self.highlighted = len(self.options) - 1
            event.stop()
        elif event.key == "enter":
            self.post_message(self.Selected(self, self.highlighted, self.options[self.highlighted]))
            event.stop()
        elif event.key == "escape":
            self.post_message(self.Cancelled(self))
            event.stop()
