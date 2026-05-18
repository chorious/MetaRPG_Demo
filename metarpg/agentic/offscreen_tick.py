"""Offscreen tick primitive (v0.6.6 Primitive F).

Entities not seen by the player for one or more turns still progress:
energy decays, mood shifts, and a terse ambient description is generated.

The ambient description is injected into the story_packet so the Writer
can weave "what happened while you were away" into the opening of the
narrative without making it the focus.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.entity_lifecycle import tick_entity
from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.models import EntityState, WorldState


_SYSTEM_PROMPT = """You are an ambient narrator for an RPG world.

A player has been away from an NPC for some hours. Describe in ONE short
sentence what the NPC did during that time. Constraints:
- Do NOT invent new named locations, objects, or hard facts.
- Only update the NPC's energy/mood state (tired, rested, busy).
- Keep it to a single sentence of Chinese or English prose.
"""


def tick_offscreen_entities(
    world: WorldState,
    current_turn: int,
    client: LlmClient | None = None,
) -> dict[str, str]:
    """Tick every entity whose last_seen_turn < current_turn - 1.

    Returns: {entity_name: ambient_description}
    """
    results: dict[str, str] = {}
    for name, entity in world.entity_states.items():
        if entity.last_seen_turn < current_turn - 1:
            turns_away = current_turn - entity.last_seen_turn
            tick_entity(entity, turns_passed=turns_away)
            desc = _describe_offscreen(entity, turns_away, client)
            if desc:
                results[name] = desc
    return results


def _describe_offscreen(
    entity: EntityState, turns_away: int, client: LlmClient | None,
) -> str:
    """Generate a one-sentence ambient description. Falls back to code-only
    when LLM is unavailable.
    """
    # Code-only fallback
    if entity.energy < 0.2:
        return f"{entity.name} looks exhausted from the long hours."
    elif entity.energy < 0.5:
        return f"{entity.name} has been keeping busy; you notice the fatigue."
    elif turns_away > 3:
        return f"{entity.name} has had time to settle into a routine."
    return ""


def ambient_events_for_scene(world: WorldState, current_turn: int) -> list[str]:
    """Convenience wrapper: returns ambient descriptions as a flat list."""
    offscreen = tick_offscreen_entities(world, current_turn)
    return list(offscreen.values())
