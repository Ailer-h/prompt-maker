"""Persisted user preferences, stored in config.json next to the app."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULTS: dict[str, Any] = {
    "output_format": "md",
    "theme": "textual-dark",
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load saved preferences, falling back to defaults for anything missing or invalid."""
    config = dict(DEFAULTS)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            config.update({key: data[key] for key in DEFAULTS if key in data})
    return config


def save_config(config: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    """Persist preferences to disk."""
    try:
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
