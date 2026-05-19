"""Load world seeds from YAML into structured objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorldSeed:
    world_id: str = ""
    title: str = ""
    genre: str = ""
    tone: dict[str, Any] = field(default_factory=dict)
    time: dict[str, Any] = field(default_factory=dict)
    canon_facts: list[dict[str, Any]] = field(default_factory=list)
    locations: dict[str, dict[str, Any]] = field(default_factory=dict)
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    beliefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    hidden_truths: dict[str, dict[str, Any]] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)
    motifs: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_hooks: dict[str, dict[str, Any]] = field(default_factory=dict)
    starting_affordances: list[str] = field(default_factory=list)


def _list_to_dict(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    """Convert a list of dicts into a dict keyed by the *id* field."""
    return {item[key]: item for item in items}


def load_seed(path: str | Path) -> WorldSeed:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return WorldSeed(
        world_id=raw.get("world_id", ""),
        title=raw.get("title", ""),
        genre=raw.get("genre", ""),
        tone=raw.get("tone", {}),
        time=raw.get("time", {}),
        canon_facts=raw.get("canon_facts", []),
        locations=raw.get("locations", {}),
        entities=raw.get("entities", {}),
        items=raw.get("items", {}),
        beliefs=_list_to_dict(raw.get("beliefs", [])),
        hidden_truths=_list_to_dict(raw.get("hidden_truths", [])),
        relations=raw.get("relations", []),
        motifs=_list_to_dict(raw.get("motifs", [])),
        active_hooks=_list_to_dict(raw.get("active_hooks", [])),
        starting_affordances=raw.get("starting_affordances", []),
    )
