"""Loading of custom Textual color themes stored as .json files in the themes folder."""
from __future__ import annotations

import json
from pathlib import Path

from textual.color import ColorParseError
from textual.theme import Theme

THEMES_DIR = Path(__file__).parent / "themes"

COLOR_FIELDS = (
    "secondary",
    "accent",
    "background",
    "surface",
    "panel",
    "foreground",
    "warning",
    "error",
    "success",
)


class ThemeError(ValueError):
    """Raised when a theme file is malformed."""


def _load_one(path: Path) -> Theme:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThemeError(f"{path.name}: {error}") from error

    primary = data.get("primary")
    if not primary:
        raise ThemeError(f"{path.name}: missing required 'primary' field")

    colors = {field: data[field] for field in COLOR_FIELDS if data.get(field)}
    theme = Theme(
        name=data.get("name", path.stem),
        primary=primary,
        dark=bool(data.get("dark", True)),
        **colors,
    )
    try:
        theme.to_color_system()
    except ColorParseError as error:
        raise ThemeError(f"{path.name}: {error}") from error
    return theme


def theme_to_data(theme: Theme, name: str | None = None) -> dict:
    """Serialize a Theme back into the on-disk JSON shape, e.g. to seed a new theme file."""
    data: dict = {"name": name or theme.name, "dark": theme.dark, "primary": theme.primary}
    for field in COLOR_FIELDS:
        value = getattr(theme, field)
        if value:
            data[field] = value
    return data


def load_themes(directory: Path = THEMES_DIR) -> list[Theme]:
    """Load every valid .json theme in a directory, sorted by name. Malformed files are skipped."""
    if not directory.is_dir():
        return []
    themes = []
    for path in sorted(directory.glob("*.json")):
        try:
            themes.append(_load_one(path))
        except ThemeError:
            continue
    return sorted(themes, key=lambda theme: theme.name.lower())
