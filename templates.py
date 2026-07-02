"""Loading and rendering of prompt templates stored as .json files."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"{{\s*(\w+)\s*}}")

TEMPLATES_DIR = Path(__file__).parent / "templates"


_FILE_SEARCH_SUFFIXES = ("_path", "_file")


@dataclass
class Variable:
    name: str
    label: str
    multiline: bool = False
    default: str = ""
    file_search: bool = False
    search_stem_override: str = ""

    def search_stem(self) -> str:
        """The base filename (without extension) to look for when file_search is set."""
        if self.search_stem_override:
            return self.search_stem_override
        for suffix in _FILE_SEARCH_SUFFIXES:
            if self.name.lower().endswith(suffix):
                return self.name[: -len(suffix)]
        return self.name


def find_file(directory: Path, stem: str) -> Path | None:
    """Look for a single top-level file named `stem.*` in directory, if any."""
    if not directory.is_dir():
        return None
    matches = sorted(path for path in directory.glob(f"{stem}.*") if path.is_file())
    return matches[0] if matches else None


def _substitute(text: str, values: dict[str, str]) -> str:
    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return PLACEHOLDER_RE.sub(substitute, text)


def _substitute_deep(obj, values: dict[str, str]):
    """Apply placeholder substitution to every string found inside a (possibly nested) structure."""
    if isinstance(obj, str):
        return _substitute(obj, values)
    if isinstance(obj, dict):
        return {key: _substitute_deep(value, values) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_substitute_deep(item, values) for item in obj]
    return obj


def _format_steps(steps: list[dict]) -> str:
    lines = []
    for index, step in enumerate(steps, start=1):
        info = step.get("stepInfo", {})
        description = info.get("description", "")
        name = step.get("stepName", f"step-{index}")
        line = f"{index}. **{name}**: {description}"
        output_file = info.get("output_file")
        if output_file:
            line += f" — output: `{output_file}`"
        lines.append(line)
    return "\n".join(lines)


@dataclass
class Template:
    path: Path
    name: str
    description: str
    body: str
    variables: list[Variable] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)

    def render_steps(self, values: dict[str, str]) -> list[dict]:
        """The template's steps with any {{placeholders}} inside them filled in."""
        return [_substitute_deep(step, values) for step in self.steps]

    def render(self, values: dict[str, str]) -> str:
        merged = {**values, "steps": _format_steps(self.render_steps(values))}
        return _substitute(self.body, merged)


class TemplateError(ValueError):
    """Raised when a template file is malformed."""


def _load_one(path: Path) -> Template:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TemplateError(f"{path.name}: {error}") from error

    if "template" not in data:
        raise TemplateError(f"{path.name}: missing required 'template' field")

    variables = [
        Variable(
            name=variable["name"],
            label=variable.get("label", variable["name"]),
            multiline=bool(variable.get("multiline", False)),
            default=str(variable.get("default", "")),
            file_search=bool(variable.get("file_search", False)),
            search_stem_override=str(variable.get("search_stem", "")),
        )
        for variable in data.get("variables", [])
    ]

    return Template(
        path=path,
        name=data.get("name", path.stem),
        description=data.get("description", ""),
        body=data["template"],
        variables=variables,
        steps=data.get("steps", []),
    )


def load_templates(directory: Path = TEMPLATES_DIR) -> list[Template]:
    """Load every .json template in a directory, sorted by display name."""
    if not directory.is_dir():
        return []
    templates = []
    for path in sorted(directory.glob("*.json")):
        templates.append(_load_one(path))
    return sorted(templates, key=lambda template: template.name.lower())
