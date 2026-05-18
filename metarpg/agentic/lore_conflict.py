"""Lore conflict primitive (v0.6.6 Primitive E).

When crystallize extracts a new fact that contradicts an existing fact,
record the pair as a "lore conflict" rather than rejecting either.

v0.6.6.1 fix: only mutex predicates trigger conflicts.
- at(X,Y)   -> nesting, not conflict (a cup can be in a tavern)
- said(X,*) -> multiple utterances are normal
- dug_by(X,Y) vs dug_by(X,Z) -> genuine mutex (one well, one origin)
"""
from __future__ import annotations

from typing import Any

from metarpg.models import Fact, WorldState


# Predicates that NEVER conflict (nesting / multi-occurrence)
_NON_MUTEX_PREDICATES = {"at", "said", "spoke", "mentioned", "observed"}


def _is_mutex_pair(existing: Fact, new_fact: Fact) -> bool:
    """Check if two facts are genuinely mutually exclusive."""
    # Same predicate required
    if existing.predicate != new_fact.predicate:
        return False

    # Non-mutex predicates always pass
    if existing.predicate in _NON_MUTEX_PREDICATES:
        return False

    # Need same subject (args[0]) and different value (args[1])
    if (
        len(existing.args) >= 2
        and len(new_fact.args) >= 2
        and existing.args[0] == new_fact.args[0]
        and existing.args[1] != new_fact.args[1]
    ):
        return True

    return False


def detect_conflict(new_fact: Fact, world: WorldState) -> list[tuple[Fact, Fact]]:
    """Find existing facts that genuinely contradict new_fact."""
    conflicts: list[tuple[Fact, Fact]] = []
    for existing in world.facts:
        if existing == new_fact:
            continue
        if _is_mutex_pair(existing, new_fact):
            conflicts.append((existing, new_fact))
    return conflicts


def record_conflict(world: WorldState, pair: tuple[Fact, Fact]) -> None:
    """Store a lore conflict pair.  Uses a canonical tuple key."""
    if not hasattr(world, "lore_conflicts"):
        world.lore_conflicts = []  # type: ignore[attr-defined]
    a, b = pair
    existing = {
        tuple(sorted([str(x[0]), str(x[1])]))
        for x in world.lore_conflicts  # type: ignore[attr-defined]
    }
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
