"""Prompt Maker: browse JSON prompt templates, fill them in, and write the result to disk."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.color import ColorParseError
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.suggester import SuggestFromList
from textual.theme import Theme
from textual.widgets import Footer, Header, Input, Label, Static, TextArea

from chat_cli.widgets import ChatWindow, FileViewer, SelectMenu
from config import load_config, save_config
from templates import TEMPLATES_DIR, Template, load_templates
from theme_changer import COLOR_FIELDS, THEMES_DIR, load_themes, theme_to_data
from widgets import TemplateForm

FillResult = tuple[dict[str, str], str, str] | None
LastRun = tuple[Template, dict[str, str], str]

OUTPUT_FORMATS = [("Markdown (.md)", "md"), ("JSON (.json)", "json")]
DEFAULT_THEME = "textual-dark"

COMMANDS = {
    "/output": "Choose the file extension (.md or .json) new prompts are saved with.",
    "/reuse": "Reopen the last template with the same field values.",
    "/newtemplate": "Create a new prompt template.",
    "/organize": "Browse, edit, or delete templates.",
    "/theme": "Choose the active color theme.",
    "/newtheme": "Create a new color theme.",
    "/themesorganize": "Browse, edit, or delete custom themes.",
    "/reloadthemes": "Reload theme files from disk (e.g. after editing one externally).",
    "/help": "List the available commands.",
}

NEW_TEMPLATE_SKELETON = """{
  "name": "New Template",
  "description": "",
  "template": "{{steps}}",
  "variables": [
    {
      "name": "example_var",
      "label": "Example variable",
      "multiline": false,
      "default": ""
    }
  ],
  "steps": []
}
"""

NEW_THEME_SKELETON = """{
  "name": "new-theme",
  "dark": true,
  "primary": "#2e3440",
  "secondary": "",
  "accent": "",
  "background": "",
  "surface": "",
  "panel": "",
  "foreground": "",
  "warning": "",
  "error": "",
  "success": ""
}
"""

THEME_PROPERTY_HELP = """\
name — identifier shown in the /theme picker.
dark — true/false; whether this is a dark-background theme (affects contrast).
primary (required) — the main color, used for headers and prominent elements.
secondary — a second color, used for less prominent highlights.
accent — a contrasting color used sparingly to draw attention, e.g. focus/cursor.
background — the app's base background color.
surface — background color of most widgets, sits above the background.
panel — background color for panel-like elements (sidebars, dialogs).
foreground — default text color.
warning — color for warning states.
error — color for error states.
success — color for success states.

Leave a value as an empty string to fall back to Textual's default for that slot."""

PREVIEW_FIELDS = ("primary", *COLOR_FIELDS)


class CommandInput(Input):
    """Command bar Input where Tab completes the current suggestion instead of changing focus."""

    BINDINGS = [Binding("tab", "accept_suggestion_or_focus_next", "Complete", show=False)]

    def action_accept_suggestion_or_focus_next(self) -> None:
        if self.cursor_at_end and self._suggestion:
            self.value = self._suggestion
            self.cursor_position = len(self.value)
        else:
            self.screen.focus_next()


class OutputFormatScreen(ModalScreen[str | None]):
    """Floating menu for picking the extension new prompt files are written with."""

    BINDINGS = [Binding("ctrl+c", "cancel", "Back", priority=True)]

    def compose(self) -> ComposeResult:
        yield SelectMenu([label for label, _ in OUTPUT_FORMATS], title="Output format")

    def on_mount(self) -> None:
        self.query_one(SelectMenu).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        message.stop()
        self.dismiss(OUTPUT_FORMATS[message.index][1])

    def on_select_menu_cancelled(self, message: SelectMenu.Cancelled) -> None:
        message.stop()
        self.dismiss(None)


class ThemeScreen(ModalScreen[str | None]):
    """Floating menu for picking the active color theme."""

    BINDINGS = [Binding("ctrl+c", "cancel", "Back", priority=True)]

    def __init__(self, theme_names: list[str]) -> None:
        super().__init__()
        self.theme_names = [DEFAULT_THEME] + theme_names
        self.options = ["Default"] + theme_names

    def compose(self) -> ComposeResult:
        yield SelectMenu(self.options, title="Theme")

    def on_mount(self) -> None:
        self.query_one(SelectMenu).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        message.stop()
        self.dismiss(self.theme_names[message.index])

    def on_select_menu_cancelled(self, message: SelectMenu.Cancelled) -> None:
        message.stop()
        self.dismiss(None)


class TemplateEditorScreen(Screen[bool]):
    """Raw JSON editor for creating a new template file, or editing an existing one."""

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("ctrl+c", "cancel", "Back", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(self, target_dir: Path, existing_path: Path | None = None) -> None:
        super().__init__()
        self.target_dir = target_dir
        self.existing_path = existing_path

    def compose(self) -> ComposeResult:
        editing = self.existing_path is not None
        filename = self.existing_path.name if self.existing_path else "new_template.json"
        content = (
            self.existing_path.read_text(encoding="utf-8") if self.existing_path else NEW_TEMPLATE_SKELETON
        )
        label = "Edit template" if editing else "New template"
        yield Label(f"{label} — filename (saved in the templates folder)")
        yield Input(filename, id="template-filename")
        yield Label("Template JSON")
        yield TextArea(content, id="template-json", language="json")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        filename = self.query_one("#template-filename", Input).value.strip()
        if not filename:
            self.notify("Filename is required", severity="error")
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"

        content = self.query_one("#template-json", TextArea).text
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            self.notify(f"Invalid JSON: {error}", severity="error")
            return
        if "template" not in data:
            self.notify("Missing required 'template' field", severity="error")
            return

        path = self.target_dir / filename
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            if self.existing_path is not None and self.existing_path != path:
                self.existing_path.unlink(missing_ok=True)
        except OSError as error:
            self.notify(f"Failed to write `{path}`: {error}", severity="error")
            return
        self.dismiss(True)


class ColorSwatch(Static, can_focus=True):
    """A single color-preview row. Click (or focus + Enter) copies its hex value to the clipboard."""

    DEFAULT_CSS = """
    ColorSwatch {
        height: 1;
    }
    ColorSwatch:focus {
        text-style: bold underline;
    }
    """

    def __init__(self, field_name: str, id: str | None = None) -> None:
        super().__init__(id=id, markup=False)
        self.field_name = field_name
        self.hex_color: str | None = None
        self._render_value()

    def set_value(self, hex_color: str | None) -> None:
        self.hex_color = hex_color
        self._render_value()

    def _render_value(self) -> None:
        text = Text()
        if self.hex_color:
            try:
                swatch_style = Style(bgcolor=self.hex_color)
            except ColorParseError:
                text.append("      ", style="dim")
            else:
                text.append("      ", style=swatch_style)
            text.append(f" {self.field_name}: {self.hex_color}")
        else:
            text.append(f"      {self.field_name}: (not set)", style="dim")
        self.update(text)

    def on_click(self) -> None:
        self._copy()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            self._copy()
            event.stop()

    def _copy(self) -> None:
        if self.hex_color:
            self.app.copy_to_clipboard(self.hex_color)
            self.notify(f"Copied {self.hex_color} to clipboard")
        else:
            self.notify(f"{self.field_name} is not set", severity="warning")


class ColorPreview(VerticalScroll):
    """Live preview of a theme's colors, refreshed as the JSON is edited."""

    def compose(self) -> ComposeResult:
        for field in PREVIEW_FIELDS:
            yield ColorSwatch(field, id=f"swatch-{field}")

    def on_mount(self) -> None:
        self.border_title = "Preview — click a color to copy it"

    def refresh_from_json(self, content: str) -> None:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        for field in PREVIEW_FIELDS:
            value = data.get(field)
            swatch = self.query_one(f"#swatch-{field}", ColorSwatch)
            swatch.set_value(value if isinstance(value, str) and value else None)


class ThemeEditorScreen(Screen[bool]):
    """Raw JSON editor for creating a new theme file, or editing an existing one."""

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("ctrl+c", "cancel", "Back", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(
        self,
        target_dir: Path,
        existing_path: Path | None = None,
        seed_theme: Theme | None = None,
    ) -> None:
        super().__init__()
        self.target_dir = target_dir
        self.existing_path = existing_path
        self.seed_theme = seed_theme

    def compose(self) -> ComposeResult:
        editing = self.existing_path is not None
        filename = self.existing_path.name if self.existing_path else "new_theme.json"
        if self.existing_path is not None:
            content = self.existing_path.read_text(encoding="utf-8")
        elif self.seed_theme is not None:
            seed_data = theme_to_data(self.seed_theme, name=f"{self.seed_theme.name}-copy")
            content = json.dumps(seed_data, indent=2, ensure_ascii=False)
        else:
            content = NEW_THEME_SKELETON
        label = "Edit theme" if editing else "New theme"
        yield Label(f"{label} — filename (saved in the themes folder)")
        yield Input(filename, id="theme-filename")
        with Horizontal(id="theme-editor-body"):
            with Vertical(id="theme-editor-json"):
                json_label = Label("Theme JSON (hover for a description of each property)")
                json_label.tooltip = THEME_PROPERTY_HELP
                yield json_label
                theme_json = TextArea(content, id="theme-json", language="json")
                theme_json.tooltip = THEME_PROPERTY_HELP
                yield theme_json
            yield ColorPreview(id="theme-preview")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_preview()

    def on_text_area_changed(self, message: TextArea.Changed) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        content = self.query_one("#theme-json", TextArea).text
        self.query_one(ColorPreview).refresh_from_json(content)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        filename = self.query_one("#theme-filename", Input).value.strip()
        if not filename:
            self.notify("Filename is required", severity="error")
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"

        content = self.query_one("#theme-json", TextArea).text
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            self.notify(f"Invalid JSON: {error}", severity="error")
            return
        if not data.get("primary"):
            self.notify("Missing required 'primary' field", severity="error")
            return

        path = self.target_dir / filename
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            if self.existing_path is not None and self.existing_path != path:
                self.existing_path.unlink(missing_ok=True)
        except OSError as error:
            self.notify(f"Failed to write `{path}`: {error}", severity="error")
            return
        self.dismiss(True)


class FillScreen(Screen[FillResult]):
    """Side-by-side template preview and fill-in form for a single template."""

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("ctrl+c", "cancel", "Back", priority=True),
        Binding("ctrl+o", "change_output", "Output format", priority=True),
    ]

    def __init__(
        self,
        template: Template,
        output_format: str,
        search_dir: Path,
        initial_values: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.template = template
        self.output_format = output_format
        self.search_dir = search_dir
        self.initial_values = initial_values

    def compose(self) -> ComposeResult:
        with Horizontal(id="fill-body"):
            yield TemplateForm(
                self.template,
                output_format=self.output_format,
                initial_values=self.initial_values,
                search_dir=self.search_dir,
                id="form",
            )
            yield FileViewer(id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#preview", FileViewer).load(self.template.path)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_change_output(self) -> None:
        self.app.push_screen(OutputFormatScreen(), self._on_output_format_result)

    def _on_output_format_result(self, result: str | None) -> None:
        if result:
            self.output_format = result
            self.app.set_output_format(result)
            self.query_one(TemplateForm).set_output_format(result)
            self.notify(f"Output format set to .{result}")
        else:
            self.notify("Output format unchanged")

    def on_template_form_cancelled(self, message: TemplateForm.Cancelled) -> None:
        self.dismiss(None)

    def on_template_form_submitted(self, message: TemplateForm.Submitted) -> None:
        self.dismiss((message.values, message.filename, self.output_format))


class OrganizeScreen(Screen[None]):
    """Full-screen template manager: browse, preview, edit, and delete templates."""

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("ctrl+c", "cancel", "Back", priority=True),
        Binding("ctrl+e", "edit_template", "Edit", priority=True),
        Binding("ctrl+x", "delete_template", "Delete", priority=True),
    ]

    def __init__(self, target_dir: Path) -> None:
        super().__init__()
        self.target_dir = target_dir
        self.templates: list[Template] = load_templates(target_dir)
        self.selected: Template | None = None

    def _options(self) -> list[str]:
        return [
            f"{template.name} — {template.description}" if template.description else template.name
            for template in self.templates
        ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="organize-body"):
            if self.templates:
                yield SelectMenu(self._options(), title="Templates", id="organize-list")
            else:
                yield Label("No templates found.", id="organize-empty")
            yield FileViewer(id="organize-preview")
        yield Footer()

    def on_mount(self) -> None:
        if self.templates:
            self.query_one("#organize-list", SelectMenu).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        message.stop()
        self.selected = self.templates[message.index]
        self.query_one("#organize-preview", FileViewer).load(self.selected.path)

    def on_select_menu_cancelled(self, message: SelectMenu.Cancelled) -> None:
        message.stop()
        self.dismiss(None)

    def action_edit_template(self) -> None:
        if self.selected is None:
            self.notify("Select a template first (Enter)", severity="warning")
            return
        self.app.push_screen(
            TemplateEditorScreen(self.target_dir, existing_path=self.selected.path),
            self._on_edit_result,
        )

    async def _on_edit_result(self, saved: bool) -> None:
        if saved:
            self.selected = None
            await self._reload()
            self.notify("Template updated.")

    async def action_delete_template(self) -> None:
        if self.selected is None:
            self.notify("Select a template first (Enter)", severity="warning")
            return
        path = self.selected.path
        try:
            path.unlink()
        except OSError as error:
            self.notify(f"Failed to delete `{path.name}`: {error}", severity="error")
            return
        self.notify(f"Deleted `{path.name}`.")
        self.selected = None
        self.query_one("#organize-preview", FileViewer).path = None
        await self._reload()

    async def _reload(self) -> None:
        self.templates = load_templates(self.target_dir)
        body = self.query_one("#organize-body", Horizontal)
        for child in list(body.query("#organize-list, #organize-empty")):
            await child.remove()
        preview = self.query_one("#organize-preview", FileViewer)
        if self.templates:
            new_list = SelectMenu(self._options(), title="Templates", id="organize-list")
            await body.mount(new_list, before=preview)
            new_list.focus()
        else:
            await body.mount(Label("No templates found.", id="organize-empty"), before=preview)


class ThemesOrganizeScreen(Screen[None]):
    """Full-screen theme manager: browse, preview, create, edit, and delete custom themes."""

    BINDINGS = [
        Binding("escape", "cancel", "Back", show=False),
        Binding("ctrl+c", "cancel", "Back", priority=True),
        Binding("ctrl+n", "new_theme", "New", priority=True),
        Binding("ctrl+e", "edit_theme", "Edit", priority=True),
        Binding("ctrl+x", "delete_theme", "Delete", priority=True),
    ]

    def __init__(self, target_dir: Path) -> None:
        super().__init__()
        self.target_dir = target_dir
        self.paths: list[Path] = sorted(target_dir.glob("*.json")) if target_dir.is_dir() else []
        self.selected: Path | None = None

    def _options(self) -> list[str]:
        return [path.name for path in self.paths]

    def compose(self) -> ComposeResult:
        with Horizontal(id="themes-organize-body"):
            if self.paths:
                yield SelectMenu(self._options(), title="Themes", id="themes-organize-list")
            else:
                yield Label("No custom themes found.", id="themes-organize-empty")
            yield FileViewer(id="themes-organize-preview")
        yield Footer()

    def on_mount(self) -> None:
        if self.paths:
            self.query_one("#themes-organize-list", SelectMenu).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        message.stop()
        self.selected = self.paths[message.index]
        self.query_one("#themes-organize-preview", FileViewer).load(self.selected)

    def on_select_menu_cancelled(self, message: SelectMenu.Cancelled) -> None:
        message.stop()
        self.dismiss(None)

    def action_new_theme(self) -> None:
        current_theme = self.app.get_theme(self.app.theme)
        self.app.push_screen(ThemeEditorScreen(self.target_dir, seed_theme=current_theme), self._on_edit_result)

    def action_edit_theme(self) -> None:
        if self.selected is None:
            self.notify("Select a theme first (Enter)", severity="warning")
            return
        self.app.push_screen(
            ThemeEditorScreen(self.target_dir, existing_path=self.selected),
            self._on_edit_result,
        )

    async def _on_edit_result(self, saved: bool) -> None:
        if saved:
            self.selected = None
            await self._reload()
            self.app.refresh_custom_themes()
            self.notify("Theme saved.")

    async def action_delete_theme(self) -> None:
        if self.selected is None:
            self.notify("Select a theme first (Enter)", severity="warning")
            return
        path = self.selected
        try:
            path.unlink()
        except OSError as error:
            self.notify(f"Failed to delete `{path.name}`: {error}", severity="error")
            return
        self.notify(f"Deleted `{path.name}`.")
        self.selected = None
        self.query_one("#themes-organize-preview", FileViewer).path = None
        await self._reload()
        self.app.refresh_custom_themes()

    async def _reload(self) -> None:
        self.paths = sorted(self.target_dir.glob("*.json")) if self.target_dir.is_dir() else []
        body = self.query_one("#themes-organize-body", Horizontal)
        for child in list(body.query("#themes-organize-list, #themes-organize-empty")):
            await child.remove()
        preview = self.query_one("#themes-organize-preview", FileViewer)
        if self.paths:
            new_list = SelectMenu(self._options(), title="Themes", id="themes-organize-list")
            await body.mount(new_list, before=preview)
            new_list.focus()
        else:
            await body.mount(Label("No custom themes found.", id="themes-organize-empty"), before=preview)


class PromptMakerApp(App):
    """Lists prompt templates; selecting one opens the fill-in form beside a preview."""

    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("slash", "focus_command", "Command", show=False),
    ]

    def __init__(self, templates_dir: Path | None = None, output_dir: Path | None = None) -> None:
        super().__init__()
        self.templates_dir = templates_dir
        self.templates = load_templates(templates_dir) if templates_dir else load_templates()
        self.output_dir = output_dir or Path.cwd()
        self.last_run: LastRun | None = None

        config = load_config()
        self.output_format = config["output_format"]

        theme_names = self._register_custom_themes()
        saved_theme = config["theme"]
        if saved_theme == DEFAULT_THEME or saved_theme in theme_names:
            self.theme = saved_theme

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        if self.templates:
            options = [
                f"{template.name} — {template.description}" if template.description else template.name
                for template in self.templates
            ]
            yield SelectMenu(options, title="Templates", id="template-list")
        yield ChatWindow(id="log")
        yield CommandInput(
            placeholder="Type a command, e.g. /output",
            suggester=SuggestFromList(COMMANDS, case_sensitive=False),
            select_on_focus=False,
            id="command",
        )
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", ChatWindow)
        if not self.templates:
            log.add_message("system", "No templates found. Add `.json` files to the templates folder.")
            return
        log.add_message(
            "system",
            "Use Up/Down to browse templates, Enter to open one, `/` for commands "
            "(try `/help`, `/newtemplate`/`/organize` for templates, `/newtheme`/`/themesorganize` "
            "for themes), Ctrl+O in the fill-in screen to change the output format, Ctrl+Q to quit.",
        )
        self.query_one("#template-list", SelectMenu).focus()

    def action_focus_command(self) -> None:
        command = self.query_one("#command", Input)
        command.focus()
        command.value += "/"
        command.cursor_position = len(command.value)

    def on_select_menu_selected(self, message: SelectMenu.Selected) -> None:
        template = self.templates[message.index]
        screen = FillScreen(template, self.output_format, self.output_dir)
        self.push_screen(screen, lambda result: self._on_fill_result(template, result))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        log = self.query_one("#log", ChatWindow)

        if text == "/output":
            self.push_screen(OutputFormatScreen(), self._on_output_format_result)
            return
        if text == "/reuse":
            if self.last_run is None:
                log.add_message("system", "No previous run to reuse yet.")
            else:
                template, values, output_format = self.last_run
                screen = FillScreen(template, output_format, self.output_dir, initial_values=values)
                self.push_screen(screen, lambda result: self._on_fill_result(template, result))
                return
        elif text == "/newtemplate":
            target_dir = self.templates_dir or TEMPLATES_DIR
            self.push_screen(TemplateEditorScreen(target_dir), self._on_template_result)
            return
        elif text == "/organize":
            target_dir = self.templates_dir or TEMPLATES_DIR
            self.push_screen(OrganizeScreen(target_dir), self._on_organize_result)
            return
        elif text == "/theme":
            theme_names = sorted(self._register_custom_themes())
            self.push_screen(ThemeScreen(theme_names), self._on_theme_result)
            return
        elif text == "/newtheme":
            current_theme = self.get_theme(self.theme)
            self.push_screen(ThemeEditorScreen(THEMES_DIR, seed_theme=current_theme), self._on_newtheme_result)
            return
        elif text == "/themesorganize":
            self.push_screen(ThemesOrganizeScreen(THEMES_DIR), self._on_themesorganize_result)
            return
        elif text == "/reloadthemes":
            self.refresh_custom_themes()
            log.add_message("system", "Reloaded themes from disk.")
        elif text == "/help":
            lines = "\n".join(f"- `{name}` — {description}" for name, description in COMMANDS.items())
            log.add_message("system", f"Available commands:\n{lines}")
        elif text:
            log.add_message("system", f"Unknown command: `{text}`. Type `/help` for a list of commands.")

        if self.templates:
            self.query_one("#template-list", SelectMenu).focus()

    def set_output_format(self, output_format: str) -> None:
        self.output_format = output_format
        self._save_preferences()

    def set_theme_preference(self, theme: str) -> None:
        self.theme = theme
        self._save_preferences()

    def _register_custom_themes(self) -> set[str]:
        custom_themes = load_themes()
        for theme in custom_themes:
            self.register_theme(theme)
        return {theme.name for theme in custom_themes}

    def refresh_custom_themes(self) -> None:
        """Re-register themes after they're created/edited/deleted; fall back if the active one vanished."""
        theme_names = self._register_custom_themes()
        if self.theme != DEFAULT_THEME and self.theme not in theme_names:
            self.set_theme_preference(DEFAULT_THEME)

    def _save_preferences(self) -> None:
        save_config({"output_format": self.output_format, "theme": self.theme})

    def _on_output_format_result(self, result: str | None) -> None:
        log = self.query_one("#log", ChatWindow)
        if result:
            self.set_output_format(result)
            log.add_message("system", f"New prompts will now be saved as `.{result}`.")
        else:
            log.add_message("system", "Output format unchanged.")
        if self.templates:
            self.query_one("#template-list", SelectMenu).focus()

    def _on_theme_result(self, result: str | None) -> None:
        log = self.query_one("#log", ChatWindow)
        if result:
            self.set_theme_preference(result)
            log.add_message("system", f"Theme set to `{result}`.")
        else:
            log.add_message("system", "Theme unchanged.")
        if self.templates:
            self.query_one("#template-list", SelectMenu).focus()

    async def _on_template_result(self, created: bool) -> None:
        log = self.query_one("#log", ChatWindow)
        if created:
            await self._refresh_template_list()
            log.add_message("system", "Template created.")
        else:
            log.add_message("system", "Template creation cancelled.")
            if self.templates:
                self.query_one("#template-list", SelectMenu).focus()

    async def _on_organize_result(self, _: None) -> None:
        await self._refresh_template_list()

    def _on_newtheme_result(self, created: bool) -> None:
        log = self.query_one("#log", ChatWindow)
        if created:
            self.refresh_custom_themes()
            log.add_message("system", "Theme created.")
        else:
            log.add_message("system", "Theme creation cancelled.")
        if self.templates:
            self.query_one("#template-list", SelectMenu).focus()

    def _on_themesorganize_result(self, _: None) -> None:
        if self.templates:
            self.query_one("#template-list", SelectMenu).focus()

    async def _refresh_template_list(self) -> None:
        self.templates = load_templates(self.templates_dir) if self.templates_dir else load_templates()
        existing = self.query("#template-list")
        if existing:
            await existing.remove()
        if not self.templates:
            return
        options = [
            f"{template.name} — {template.description}" if template.description else template.name
            for template in self.templates
        ]
        menu = SelectMenu(options, title="Templates", id="template-list")
        await self.mount(menu, before=self.query_one("#log"))
        menu.focus()

    def _on_fill_result(self, template: Template, result: FillResult) -> None:
        log = self.query_one("#log", ChatWindow)
        if result is None:
            log.add_message("system", f"Cancelled `{template.name}`.")
        else:
            values, filename, output_format = result
            output_path = self.output_dir / filename
            if output_path.suffix.lower() == ".json":
                data = {"template": template.name, **values}
                if template.steps:
                    data["steps"] = template.render_steps(values)
                content = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                content = template.render(values)
            try:
                output_path.write_text(content, encoding="utf-8")
            except OSError as error:
                log.add_message("system", f"Failed to write `{output_path}`: {error}")
            else:
                log.add_message("system", f"Created `{output_path}`.")
                self.last_run = (template, values, output_format)
        self.query_one("#template-list", SelectMenu).focus()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill in JSON prompt templates and write the result to disk.")
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Directory of .json templates to use instead of the bundled templates folder.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory new prompt files are written to. Defaults to the current working directory.",
    )
    args = parser.parse_args()
    PromptMakerApp(templates_dir=args.templates, output_dir=args.output_dir).run()


if __name__ == "__main__":
    main()
