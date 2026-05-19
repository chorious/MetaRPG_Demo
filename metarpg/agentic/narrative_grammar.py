"""Load narrative grammar from YAML into structured objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class NarrativeGrammar:
    version: str = ""
    name: str = ""
    commitment_levels: dict[str, dict[str, Any]] = field(default_factory=dict)
    hook_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    hint_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    beat_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    motif_rules: dict[str, Any] = field(default_factory=dict)
    render_rules: dict[str, Any] = field(default_factory=dict)


def load_grammar(path: str | Path) -> NarrativeGrammar:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return NarrativeGrammar(
        version=raw.get("version", ""),
        name=raw.get("name", ""),
        commitment_levels=raw.get("commitment_levels", {}),
        hook_types=raw.get("hook_types", {}),
        hint_types=raw.get("hint_types", {}),
        beat_types=raw.get("beat_types", {}),
        motif_rules=raw.get("motif_rules", {}),
        render_rules=raw.get("render_rules", {}),
    )
