"""Snapshot export — v0.5.1.

Export WorldState into player-visible, UPF-panel, and debug tiers.
"""
from __future__ import annotations

from typing import Any

from .models import Fact, WorldState


def export_snapshot(world: WorldState) -> dict[str, Any]:
    """Full snapshot for the bridge response."""
    return {
        "player_visible": _player_visible(world),
        "upf_panels": _upf_panels(world),
        "debug": _debug_surface(world),
    }


def _player_visible(world: WorldState) -> dict[str, Any]:
    """What the player character can directly perceive."""
    loc = _player_location(world)
    nearby = _nearby_npcs(world)
    return {
        "location": loc,
        "nearby_npcs": nearby,
        "known_facts": [str(f) for f in world.facts if _fact_is_public(f)],
        "visible_locations": sorted(world.locations),
    }


def _upf_panels(world: WorldState) -> dict[str, Any]:
    """Data that can populate UPF panels."""
    loc = _player_location(world)
    return {
        "location": loc,
        "npcs": sorted(world.npcs),
        "relations": [
            {
                "from": r.from_agent,
                "to": r.to_agent,
                "dimensions": r.dimensions,
            }
            for r in world.relations.values()
        ],
        "beliefs": [
            {"id": b.id, "description": b.description, "prob": b.prob}
            for b in world.beliefs.values()
        ],
        "inventory": _player_inventory(world),
    }


def _debug_surface(world: WorldState) -> dict[str, Any]:
    """Internal state for debug panel."""
    active_frontiers: list[dict[str, Any]] = []
    if hasattr(world, "frontiers"):
        active_frontiers = [
            {
                "id": f.id,
                "kind": f.kind.value,
                "anchor": f.anchor_entity,
                "status": f.status.value,
                "salience": f.salience,
            }
            for f in world.frontiers.values()
            if f.status.value != "frozen"
        ]

    active_hooks: list[str] = []
    if hasattr(world, "hooks"):
        active_hooks = [
            h.id for h in world.hooks.values()
            if not h.consumed and h.ttl > 0
        ]

    return {
        "turn": world.turn,
        "fact_count": len(world.facts),
        "knowledge_count": len(world.knowledge),
        "relation_count": len(world.relations),
        "belief_count": len(world.beliefs),
        "frontier_count": len(active_frontiers),
        "active_frontiers": active_frontiers,
        "active_hooks": active_hooks,
    }


# ---------- helpers ----------


def _player_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _nearby_npcs(world: WorldState) -> list[str]:
    loc = _player_location(world)
    return sorted(
        f.args[0] for f in world.facts
        if f.predicate == "at" and len(f.args) == 2
        and f.args[1] == loc and f.args[0] in world.npcs
    )


def _player_inventory(world: WorldState) -> list[str]:
    return sorted(
        f.args[1] for f in world.facts
        if f.predicate == "has" and len(f.args) == 2 and f.args[0] == "player"
    )


def _fact_is_public(f: Fact) -> bool:
    """Suppress internal-only facts from player view."""
    # Hide at() facts (location is shown separately)
    if f.predicate == "at":
        return False
    return True
