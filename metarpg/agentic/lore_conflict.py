"""Lore conflict primitive (v0.6.6 Primitive E).

When crystallize extracts a new fact that contradicts an existing fact,
record the pair as a "lore conflict" rather than rejecting either.

Conflicts are surfaced to the Writer as narrative opportunities:
NPCs may hesitate, deflect, or subtly contradict earlier statements.
"""
from __future__ import annotations

from typing import Any

from metarpg.models import Fact, WorldState


def detect_conflict(new_fact: Fact, world: WorldState) -> list[tuple[Fact, Fact]]:
    """Find existing facts that contradict new_fact.

    Simple heuristic: same predicate, overlapping args[0] (subject),
    different args[1] (object/value).  E.g.:
      well_dug_by(mara_grandfather)  vs  well_dug_by(community)
    """
    conflicts: list[tuple[Fact, Fact]] = []
    for existing in world.facts:
        if existing == new_fact:
            continue
        if existing.predicate != new_fact.predicate:
            continue
        # Same predicate: check if first arg matches but second differs
        if (
            len(existing.args) >= 2
            and len(new_fact.args) >= 2
            and existing.args[0] == new_fact.args[0]
            and existing.args[1] != new_fact.args[1]
        ):
            conflicts.append((existing, new_fact))
    return conflicts


def record_conflict(world: WorldState, pair: tuple[Fact, Fact]) -> None:
    """Store a lore conflict pair.  Uses a canonical tuple key."""
    if not hasattr(world, "lore_conflicts"):
        world.lore_conflicts = []  # type: ignore[attr-defined]
    a, b = pair
    key = (str(a), str(b))
    # Simple dedup
    existing = {tuple(sorted([str(x[0]), str(x[1])])) for x in world.lore_conflicts}  # type: ignore[attr-defined]
    if tuple(sorted([str(a), str(b)])) not in existing:
        world.lore_conflicts.append(pair)  # type: ignore[attr-defined]


def get_conflict_surface(world: WorldState) -> list[dict[str, Any]]:
    """Serialize lore conflicts for story_packet."""
    if not hasattr(world, "lore_conflicts"):
        return []
    return [
        {"fact_a": str(a), "fact_b": str(b)}
        for a, b in world.lore_conflicts  # type: ignore[attr-defined]
    ]
