"""Form widget for filling in a template's variables before writing it out."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import events
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Input, Label, TextArea

from templates import Template, find_file


def _slugify(name: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in name.strip().lower()).strip("_") or "prompt"


def default_filename(template: Template, output_format: str = "md") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{_slugify(template.name)}_{stamp}.{output_format}"


class TemplateForm(VerticalScroll):
    """One labeled field per template variable, plus an output filename field."""

    DEFAULT_CSS = """
    TemplateForm {
        border: round $secondary;
        padding: 0 1;
    }
    TemplateForm Label {
        margin-top: 1;
    }
    TemplateForm TextArea {
        height: 5;
    }
    TemplateForm #filename {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "confirm_form", "Create", priority=True),
        Binding("ctrl+backspace,alt+backspace", "delete_word_left", "Delete word left", show=False, priority=True),
    ]

    class Submitted(Message):
        """Posted when the user confirms the form."""

        def __init__(self, form: "TemplateForm", values: dict[str, str], filename: str) -> None:
            self.form = form
            self.values = values
            self.filename = filename
            super().__init__()

    class Cancelled(Message):
        """Posted when the user backs out with Escape."""

        def __init__(self, form: "TemplateForm") -> None:
            self.form = form
            super().__init__()

    def __init__(
        self,
        template: Template,
        *,
        output_format: str = "md",
        initial_values: dict[str, str] | None = None,
        search_dir: Path | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.template = template
        self.output_format = output_format
        self.initial_values = initial_values or {}
        self.search_dir = search_dir
        self.border_title = f"Fill in — {template.name}"

    def compose(self):
        for variable in self.template.variables:
            yield Label(variable.label)
            value = self._initial_value_for(variable)
            if variable.multiline:
                yield TextArea(value, id=f"field-{variable.name}")
            else:
                yield Input(value, id=f"field-{variable.name}")
        yield Label("Output filename")
        yield Input(default_filename(self.template, self.output_format), id="filename")

    def _initial_value_for(self, variable) -> str:
        if variable.name in self.initial_values:
            return self.initial_values[variable.name]
        if variable.default:
            return variable.default
        if variable.file_search and self.search_dir is not None:
            found = find_file(self.search_dir, variable.search_stem())
            if found is not None:
                return str(found)
        return ""

    def on_mount(self) -> None:
        if self.template.variables:
            first = self.template.variables[0]
            self.query_one(f"#field-{first.name}").focus()
        else:
            self.query_one("#filename", Input).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.post_message(self.Cancelled(self))
            event.stop()

    def action_confirm_form(self) -> None:
        self._submit()

    def set_output_format(self, output_format: str) -> None:
        """Switch the suggested output extension without touching a manually edited base name."""
        self.output_format = output_format
        filename_input = self.query_one("#filename", Input)
        stem = filename_input.value.rsplit(".", 1)[0] if "." in filename_input.value else filename_input.value
        filename_input.value = f"{stem}.{output_format}"

    def action_delete_word_left(self) -> None:
        # Input's own ctrl+backspace binding deletes the word to the *right* of the
        # cursor, not the left, so route it to the correct action on whichever
        # field is focused instead of relying on Input's default.
        focused = self.app.focused
        if isinstance(focused, Input):
            focused.action_delete_left_word()
        elif isinstance(focused, TextArea):
            focused.action_delete_word_left()

    def _submit(self) -> None:
        values: dict[str, str] = {}
        for variable in self.template.variables:
            field = self.query_one(f"#field-{variable.name}")
            values[variable.name] = field.text if isinstance(field, TextArea) else field.value
        filename = self.query_one("#filename", Input).value.strip() or default_filename(
            self.template, self.output_format
        )
        self.post_message(self.Submitted(self, values, filename))
