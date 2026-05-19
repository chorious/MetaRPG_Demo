"""Build RenderBrief from validated transaction, world diff, and narrative frame."""
from __future__ import annotations

from typing import Any

from metarpg.agentic.transaction import NarrativeFrame, RenderBrief, TurnTransaction
from metarpg.models import WorldState


def build_render_brief(
    tx: TurnTransaction,
    frame: NarrativeFrame,
    world: WorldState,
) -> RenderBrief:
    """Assemble the brief that DeepSeek Flash will render into prose.

    Args:
        tx: The validated TurnTransaction (already committed).
        frame: The NarrativeFrame from HookManager.
        world: Current WorldState after commit (used to read recent events).
    """
    events = getattr(world, "events", [])
    recent_events = [
        e.get("summary", e.get("description", ""))
        for e in events[-3:]
        if e.get("summary") or e.get("description")
    ]

    # v0.7.3: extract player location and visible/absent entities from world facts
    player_location = _get_player_location(world)
    visible_entities = _get_visible_entities(world, player_location)
    absent_entities = _get_absent_entities(world, visible_entities)

    # v0.7.4: current-turn obligation to prevent stale-context rendering
    obligation = _build_current_turn_obligation(tx)

    return RenderBrief(
        committed_events=recent_events,
        visible_reactions=[],
        allowed_hints=list(frame.candidate_hints),
        motifs_to_render=list(frame.motifs_to_use),
        style_constraints=[],
        forbidden_claims=list(tx.forbidden_claims),
        # v0.7.3 grounding fields
        player_location=player_location,
        visible_entities=visible_entities,
        visible_objects=[],  # TODO: populate from world.items if needed
        absent_entities=absent_entities,
        # v0.7.4 current-turn obligation
        current_turn_obligation=obligation,
    )


def _build_current_turn_obligation(tx: TurnTransaction) -> dict[str, Any]:
    """Build the current-turn obligation dict from transaction metadata."""
    # Infer source from assumptions (set by runner branches)
    source = "director"
    if tx.assumptions:
        source = tx.assumptions[0].get("source", "director")

    action_type = tx.player_intent.get("action_type", "")
    target_ids = tx.player_intent.get("targets", [])

    obligation: dict[str, Any] = {
        "player_input": tx.player_input,
        "action_type": action_type,
        "target_ids": target_ids,
        "source": source,
    }

    if source == "absence_response":
        obligation["response_mode"] = "absence"
        obligation["must_address"] = ["目标不在场/不可达"]
        obligation["must_not_claim"] = ["不要渲染前一回合的动作成功"]
    elif source == "deterministic_movement":
        obligation["response_mode"] = "normal"
        obligation["must_address"] = ["玩家移动到目的地"]
    elif source == "fallback":
        obligation["response_mode"] = "fallback"
        obligation["must_address"] = ["承认动作无法推进或只给 minimal texture"]
        obligation["must_not_claim"] = [
            "不要渲染前一回合的动作成功",
            "不要声称新状态变化发生",
        ]
    elif source == "unreachable_location_response":
        obligation["response_mode"] = "unreachable"
        obligation["must_address"] = ["目标地点存在但当前无法直接到达"]
        obligation["must_not_claim"] = ["不要渲染玩家已成功到达该地点"]
    else:
        obligation["response_mode"] = "normal"

    return obligation


def _get_player_location(world: WorldState) -> str:
    """Return the player's current location from world facts."""
    for f in world.facts:
        if f.predicate == "at" and len(f.args) >= 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _get_visible_entities(world: WorldState, player_location: str) -> list[str]:
    """Return entities that share the player's location."""
    visible = []
    if not player_location:
        return visible
    for f in world.facts:
        if (
            f.predicate == "at"
            and len(f.args) >= 2
            and f.args[0] != "player"
            and f.args[1] == player_location
        ):
            visible.append(f.args[0])
    return visible


def _get_absent_entities(world: WorldState, visible_entities: list[str]) -> list[str]:
    """Return known NPCs that are NOT in the player's current location."""
    visible_set = set(visible_entities)
    absent = []
    for npc in sorted(world.npcs):
        if npc not in visible_set:
            absent.append(npc)
    return absent
