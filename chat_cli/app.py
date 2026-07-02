"""Demo CLI chat app, wiring up ChatWindow, FileViewer, and SelectMenu."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input

from widgets import ChatWindow, FileViewer, SelectMenu

MODEL_OPTIONS = [
    "claude-sonnet-5",
    "claude-opus-4.8",
    "claude-haiku-4.5",
    "claude-fable-5",
]


class MenuScreen(ModalScreen[str | None]):
    """Modal overlay hosting a SelectMenu, resolving to the chosen value (or None)."""

    def __init__(self, options: list[str], title: str) -> None:
        super().__init__()
        self.options = options
        self.title_text = title

    def compose(self) -> ComposeResult:
        yield SelectMenu(self.options, title=self.title_text)

    def on_mount(self) -> None:
        self.query_one(SelectMenu).focus()

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        self.dismiss(message.value)

    def on_select_menu_cancelled(self, message: SelectMenu.Cancelled) -> None:
        self.dismiss(None)


class ChatCLIApp(App):
    """A small Claude-Code-style terminal chat interface."""

    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+m", "open_menu", "Model menu"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield ChatWindow(id="chat")
            yield FileViewer(id="viewer")
        yield Input(placeholder="Type a message, or /open <path>, /menu, /quit", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        chat = self.query_one("#chat", ChatWindow)
        chat.add_message(
            "system",
            "Welcome! Try `/open <file>` to view a file, `/menu` (or Ctrl+M) to "
            "pick a model, or just type a message.",
        )
        self.query_one("#prompt", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return

        chat = self.query_one("#chat", ChatWindow)

        if text.startswith("/open "):
            path = text.removeprefix("/open ").strip()
            self.query_one("#viewer", FileViewer).load(path)
            chat.add_message("system", f"Loaded `{path}` into the file viewer.")
        elif text == "/menu":
            self.action_open_menu()
        elif text == "/quit":
            self.exit()
        else:
            chat.add_message("user", text)
            chat.add_message("assistant", f"(demo echo) You said: {text}")

        self.query_one("#prompt", Input).focus()

    def action_open_menu(self) -> None:
        self.push_screen(MenuScreen(MODEL_OPTIONS, "Select a model"), self._on_menu_result)

    def _on_menu_result(self, result: str | None) -> None:
        chat = self.query_one("#chat", ChatWindow)
        if result:
            chat.add_message("system", f"Model set to **{result}**.")
        else:
            chat.add_message("system", "Menu cancelled.")
        self.query_one("#prompt", Input).focus()


def main() -> None:
    ChatCLIApp().run()


if __name__ == "__main__":
    main()
