"""Frontier registry — v0.5.

A frontier is a compressed region of the world worth expanding.
When player attention touches a frontier, the system generates
affordance candidates only for that boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import MetaAct, WorldState


class FrontierKind(Enum):
    """Types of expansion boundaries."""

    SCENE_BOUNDARY = "scene_boundary"
    SALIENT_OBJECT = "salient_object"
    UNQUERIED_NPC = "unqueried_npc"
    ACTIVE_SOCIAL_TENSION = "active_social_tension"
    UNKNOWN_CAUSAL_PATH = "unknown_causal_path"
    LATENT_HOOK = "latent_hook"
    UNRESOLVED_GOAL = "unresolved_goal"
    NEW_TOOL_POSSIBILITY = "new_tool_possibility"
    INSTITUTIONAL_RULE_BOUNDARY = "institutional_rule_boundary"
    THREAT_BOUNDARY = "threat_boundary"


class FrontierStatus(Enum):
    """Lifecycle states of a frontier."""

    COMPRESSED = "compressed"    # not yet expanded
    EXPANDING = "expanding"      # currently generating affordances
    EXPANDED = "expanded"        # affordances already surfaced
    FROZEN = "frozen"            # deliberately locked


@dataclass
class Frontier:
    """A compressed region of the world now worth expanding."""

    id: str
    kind: FrontierKind
    anchor_entity: str = ""       # what this frontier is anchored to
    location: str = ""            # where this frontier exists
    source_event: str = ""        # what created this frontier
    status: FrontierStatus = FrontierStatus.COMPRESSED
    salience: float = 0.5         # 0.0–1.0, how attention-worthy
    uncertainty: float = 0.5      # 0.0–1.0, how much is unknown
    expected_reuse: float = 0.5   # 0.0–1.0, likely future value
    risk: float = 0.0             # 0.0–1.0, danger of expansion
    budget_hint: str = "small"    # none/small/medium/large/emergency
    created_turn: int = 0
    last_touched_turn: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------- registry API ----------


def create_frontier(
    world: WorldState,
    kind: FrontierKind,
    anchor: str,
    location: str,
    source_event: str,
    salience: float = 0.5,
    uncertainty: float = 0.5,
    budget_hint: str = "small",
) -> Frontier:
    """Register a new frontier in world state."""
    fid = _unique_frontier_id(world, kind.value)
    f = Frontier(
        id=fid,
        kind=kind,
        anchor_entity=anchor,
        location=location,
        source_event=source_event,
        salience=salience,
        uncertainty=uncertainty,
        budget_hint=budget_hint,
        created_turn=world.turn,
        last_touched_turn=world.turn,
    )
    if not hasattr(world, "frontiers"):
        world.frontiers = {}
    world.frontiers[fid] = f
    return f


def touch_frontier(world: WorldState, meta: MetaAct) -> list[Frontier]:
    """Find frontiers touched by a player action.

    Returns active frontiers that overlap with the action's location,
    entities, or topics.
    """
    if not hasattr(world, "frontiers"):
        return []

    touched: list[Frontier] = []
    loc = meta.player_location
    nearby = set(meta.local_entities)
    text = meta.raw_text.lower()

    for f in world.frontiers.values():
        if f.status == FrontierStatus.FROZEN:
            continue

        score = 0.0
        # Location match (lower weight so same-location frontiers don't auto-trigger)
        if f.location and f.location == loc:
            score += 0.15
        # Entity match
        if f.anchor_entity in nearby or f.anchor_entity in text:
            score += 0.35
        # Topic match in text
        if f.source_event and any(kw in text for kw in f.source_event.split("_")):
            score += 0.2
        # Kind-specific keyword boost
        if f.location == loc:
            if f.kind == FrontierKind.SCENE_BOUNDARY and any(k in text for k in ("去", "前往", "进入", "go", "enter", "move", "推门", "走到", "到达")):
                score += 0.5
            if f.kind == FrontierKind.SALIENT_OBJECT and any(k in text for k in ("找", "捡", "拿", "用", "find", "pick", "use", "查看", "inspect")):
                score += 0.5
            if f.kind == FrontierKind.UNQUERIED_NPC and any(k in text for k in ("问", "说", "告诉", "ask", "tell", "talk", "speak", "对话")):
                score += 0.5
            if f.kind == FrontierKind.UNKNOWN_CAUSAL_PATH and any(k in text for k in ("为什么", "怎么回事", "why", "how", "调查", "investigate")):
                score += 0.5
        # Salience boost
        score += f.salience * 0.05

        if score >= 0.3:
            f.last_touched_turn = world.turn
            touched.append(f)

    # Sort by salience descending
    touched.sort(key=lambda x: x.salience, reverse=True)
    return touched


def mark_expanding(world: WorldState, frontier_id: str) -> None:
    if hasattr(world, "frontiers") and frontier_id in world.frontiers:
        world.frontiers[frontier_id].status = FrontierStatus.EXPANDING


def mark_expanded(world: WorldState, frontier_id: str) -> None:
    if hasattr(world, "frontiers") and frontier_id in world.frontiers:
        world.frontiers[frontier_id].status = FrontierStatus.EXPANDED


def freeze_frontier(world: WorldState, frontier_id: str, reason: str = "") -> None:
    if hasattr(world, "frontiers") and frontier_id in world.frontiers:
        world.frontiers[frontier_id].status = FrontierStatus.FROZEN
        world.frontiers[frontier_id].metadata["freeze_reason"] = reason


def decay_frontiers(world: WorldState) -> list[str]:
    """Decay or expire old frontiers. Returns list of removed ids."""
    if not hasattr(world, "frontiers"):
        return []

    removed: list[str] = []
    for fid, f in list(world.frontiers.items()):
        age = world.turn - f.last_touched_turn
        if age > 10 and f.status == FrontierStatus.EXPANDED:
            removed.append(fid)
            del world.frontiers[fid]
        elif age > 5 and f.status == FrontierStatus.COMPRESSED:
            f.salience = max(0.0, f.salience - 0.1)
            if f.salience < 0.1:
                removed.append(fid)
                del world.frontiers[fid]
    return removed


def get_active_frontiers(world: WorldState) -> list[Frontier]:
    """Return all non-frozen frontiers."""
    if not hasattr(world, "frontiers"):
        return []
    return [
        f for f in world.frontiers.values()
        if f.status != FrontierStatus.FROZEN
    ]


# ---------- utilities ----------

_frontier_counter: dict[str, int] = {}


def _unique_frontier_id(world: WorldState, prefix: str) -> str:
    existing = [k for k in world.frontiers if k.startswith(f"F_{prefix}_")] if hasattr(world, "frontiers") else []
    idx = len(existing) + 1
    return f"F_{prefix}_{idx}"
