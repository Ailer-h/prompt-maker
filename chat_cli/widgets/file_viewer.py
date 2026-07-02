"""Widget that displays the contents of a file with syntax highlighting."""
from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static


class FileViewer(VerticalScroll):
    """Scrollable, syntax-highlighted view of a single file."""

    DEFAULT_CSS = """
    FileViewer {
        border: round $accent;
        padding: 0 1;
    }
    """

    path: reactive[Path | None] = reactive(None)

    def compose(self):
        yield Static(id="file-viewer-body")

    def watch_path(self, path: Path | None) -> None:
        body = self.query_one("#file-viewer-body", Static)
        if path is None:
            body.update("[dim]No file loaded[/]")
            self.border_title = "File"
            return

        self.border_title = str(path)
        if not path.exists():
            body.update(f"[red]No such file: {path}[/]")
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            body.update(f"[red]Could not read {path}: {error}[/]")
            return

        lexer = Syntax.guess_lexer(str(path), code=text)
        body.update(Syntax(text, lexer, line_numbers=True, word_wrap=False, indent_guides=True))

    def load(self, file_path: str | Path) -> None:
        """Load a new file into the viewer."""
        self.path = Path(file_path).expanduser()
