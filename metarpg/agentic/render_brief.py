"""Build RenderBrief from validated transaction, world diff, and narrative frame."""
from __future__ import annotations

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
    )


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
