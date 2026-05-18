"""Entity lifecycle primitive (v0.6.6).

Every named entity (NPC or object) tracked in world.entity_states gets
energy/mood/life_state.  Energy decays per turn; mood shifts when energy
crosses thresholds.

New entities are auto-initialised when first mentioned by the Writer and
recognised during commit/crystallize.
"""
from __future__ import annotations

from typing import Any

from metarpg.models import EntityState, WorldState


_ENERGY_DECAY_PER_TURN = 0.05
_LOW_ENERGY_THRESHOLD = 0.3
_CRITICAL_ENERGY_THRESHOLD = 0.1


def tick_entity(entity: EntityState, turns_passed: int = 1) -> None:
    """Decay energy and update derived mood."""
    entity.energy = max(0.0, entity.energy - _ENERGY_DECAY_PER_TURN * turns_passed)
    _update_mood(entity)


def _update_mood(entity: EntityState) -> None:
    if entity.energy < _CRITICAL_ENERGY_THRESHOLD:
        entity.mood = "exhausted"
    elif entity.energy < _LOW_ENERGY_THRESHOLD:
        entity.mood = "tired"
    else:
        entity.mood = "neutral"


def ensure_entity(world: WorldState, name: str) -> EntityState:
    """Get existing EntityState or create a default one."""
    if name not in world.entity_states:
        world.entity_states[name] = EntityState(name=name)
    return world.entity_states[name]


def tick_all_present(world: WorldState, present_names: set[str]) -> None:
    """Tick every entity that is currently visible to the player."""
    turn = world.world_time.get("turn", 0)
    for name in present_names:
        entity = ensure_entity(world, name)
        tick_entity(entity)
        entity.last_seen_turn = turn
        # location from world facts
        entity.last_seen_location = _entity_location(world, name)


def _entity_location(world: WorldState, entity_name: str) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == entity_name:
            return f.args[1]
    return ""


def surface_for_npc(entity: EntityState) -> dict[str, Any]:
    """What the Writer sees about an NPC."""
    return {
        "energy": round(entity.energy, 2),
        "mood": entity.mood,
        "life_state": entity.life_state,
    }
