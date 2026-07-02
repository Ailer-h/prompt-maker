"""Scrolling chat window widget."""
from __future__ import annotations

from datetime import datetime

from rich.markdown import Markdown
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

ROLE_STYLES = {
    "user": ("you", "bold cyan"),
    "assistant": ("assistant", "bold green"),
    "system": ("system", "dim italic yellow"),
}


class ChatMessage(Static):
    """A single rendered chat entry with a role/time header and markdown body."""

    def __init__(self, role: str, content: str) -> None:
        super().__init__()
        self.role = role
        self.content_text = content
        self.add_class(f"role-{role}" if role in ROLE_STYLES else "role-other")

    def compose(self):
        label, style = ROLE_STYLES.get(self.role, (self.role, "bold white"))
        timestamp = datetime.now().strftime("%H:%M:%S")
        yield Static(Text(f"{label} · {timestamp}", style=style), classes="chat-message-header")
        yield Static(Markdown(self.content_text), classes="chat-message-body")


class ChatWindow(VerticalScroll):
    """A scrollable chat history that auto-scrolls to the newest message."""

    DEFAULT_CSS = """
    ChatWindow {
        border: round $primary;
        padding: 0 1;
    }
    ChatWindow .chat-message-header {
        margin-top: 1;
    }
    ChatWindow .chat-message-body {
        margin-left: 2;
    }
    """

    def add_message(self, role: str, content: str) -> ChatMessage:
        """Append a message and scroll the window to reveal it."""
        message = ChatMessage(role, content)
        self.mount(message)
        self.call_after_refresh(self.scroll_end, animate=False)
        return message
