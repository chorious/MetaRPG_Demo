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

    # v0.7.1: runtime alias index, built once after loading
    _alias_index: dict[str, list[tuple[str, str]]] = field(
        default_factory=dict, repr=False
    )

    def _build_alias_index(self) -> None:
        """Build a reverse index: alias phrase -> list of (canonical_id, kind)."""
        index: dict[str, list[tuple[str, str]]] = {}

        def add_aliases(
            obj_id: str, kind: str, aliases: list[str]
        ) -> None:
            for alias in aliases:
                alias = alias.strip().lower()
                if not alias:
                    continue
                index.setdefault(alias, []).append((obj_id, kind))

        # Locations
        for loc_id, loc in self.locations.items():
            aliases = loc.get("aliases", [])
            # also index the canonical id itself and the display name
            aliases = [loc_id.replace("_", " "), loc.get("name", "")] + aliases
            add_aliases(loc_id, "location", aliases)

        # Entities
        for ent_id, ent in self.entities.items():
            aliases = ent.get("aliases", [])
            aliases = [ent_id.replace("_", " "), ent.get("visible_name", "")] + aliases
            add_aliases(ent_id, "entity", aliases)

        # Items
        for item_id, item in self.items.items():
            aliases = item.get("aliases", [])
            aliases = [item_id.replace("_", " "), item.get("name", "")] + aliases
            add_aliases(item_id, "item", aliases)

        # Active hooks
        for hook_id, hook in self.active_hooks.items():
            aliases = hook.get("aliases", [])
            aliases = [hook_id.replace("_", " "), hook.get("label", "")] + aliases
            add_aliases(hook_id, "hook", aliases)

        # Motifs
        for motif_id, motif in self.motifs.items():
            aliases = motif.get("aliases", [])
            aliases = [motif_id.replace("_", " "), motif.get("label", "")] + aliases
            add_aliases(motif_id, "motif", aliases)

        self._alias_index = index

    def resolve_alias(
        self, mention: str
    ) -> list[tuple[str, str, float]]:
        """Resolve a mention to canonical ID(s) via exact alias phrase match.

        Returns list of (canonical_id, kind, confidence).
        Empty list if no match. Multiple entries if ambiguous.
        """
        if not self._alias_index:
            self._build_alias_index()

        mention_clean = mention.strip().lower()
        results: list[tuple[str, str, float]] = []

        # Strategy 1: exact alias phrase match
        if mention_clean in self._alias_index:
            candidates = self._alias_index[mention_clean]
            seen: set[str] = set()
            for canonical_id, kind in candidates:
                key = f"{canonical_id}:{kind}"
                if key in seen:
                    continue
                seen.add(key)
                results.append((canonical_id, kind, 0.95))
            return results

        # Strategy 2: mention contains a known alias (multi-word containment)
        # Only for phrases >= 2 chars to avoid noise
        seen: set[str] = set()
        if len(mention_clean) >= 2:
            for alias, candidates in self._alias_index.items():
                if len(alias) >= 2 and alias in mention_clean:
                    for canonical_id, kind in candidates:
                        key = f"{canonical_id}:{kind}"
                        if key in seen:
                            continue
                        seen.add(key)
                        # Containment match is slightly lower confidence
                        results.append((canonical_id, kind, 0.85))

        # Deduplicate while preserving highest confidence
        best: dict[str, tuple[str, str, float]] = {}
        for cid, kind, conf in results:
            key = f"{cid}:{kind}"
            if key not in best or best[key][2] < conf:
                best[key] = (cid, kind, conf)

        return list(best.values())

    def get_aliases_for(self, canonical_id: str) -> list[str]:
        """Return all alias phrases registered for a canonical ID."""
        if not self._alias_index:
            self._build_alias_index()
        aliases: list[str] = []
        for alias, candidates in self._alias_index.items():
            for cid, _kind in candidates:
                if cid == canonical_id:
                    aliases.append(alias)
        return aliases


def _list_to_dict(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    """Convert a list of dicts into a dict keyed by the *id* field."""
    return {item[key]: item for item in items}


def load_seed(path: str | Path) -> WorldSeed:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    seed = WorldSeed(
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
    seed._build_alias_index()
    return seed
