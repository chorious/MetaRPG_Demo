"""Tests for entity_lifecycle primitive (v0.6.6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.entity_lifecycle import (
    ensure_entity,
    surface_for_npc,
    tick_all_present,
    tick_entity,
)
from metarpg.agentic.story_packet import build_story_packet
from metarpg.models import EntityState, Fact, WorldState


def _world() -> WorldState:
    w = WorldState()
    w.npcs = {"mara"}
    w.locations = {"tavern"}
    w.facts.add(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("at", ("mara", "tavern")))
    return w


def test_energy_decays_over_turns() -> None:
    e = EntityState(name="mara", energy=1.0)
    tick_entity(e)
    assert e.energy < 1.0
    assert e.energy == 0.95


def test_mood_becomes_tired_below_0_3() -> None:
    e = EntityState(name="mara", energy=0.25)
    tick_entity(e)
    assert e.mood == "tired"


def test_mood_becomes_exhausted_below_0_1() -> None:
    e = EntityState(name="mara", energy=0.08)
    tick_entity(e)
    assert e.mood == "exhausted"


def test_energy_never_drops_below_zero() -> None:
    e = EntityState(name="mara", energy=0.01)
    for _ in range(10):
        tick_entity(e)
    assert e.energy == 0.0


def test_ensure_entity_creates_default() -> None:
    w = _world()
    e = ensure_entity(w, "new_guy")
    assert e.name == "new_guy"
    assert e.energy == 1.0
    assert e.mood == "neutral"
    assert "new_guy" in w.entity_states


def test_ensure_entity_returns_existing() -> None:
    w = _world()
    w.entity_states["mara"] = EntityState(name="mara", energy=0.5)
    e = ensure_entity(w, "mara")
    assert e.energy == 0.5


def test_surface_for_npc_exposes_energy_and_mood() -> None:
    e = EntityState(name="mara", energy=0.72, mood="neutral", life_state="alive")
    s = surface_for_npc(e)
    assert s["energy"] == 0.72
    assert s["mood"] == "neutral"
    assert s["life_state"] == "alive"


def test_tick_all_present_updates_last_seen() -> None:
    w = _world()
    w.world_time = {"turn": 5, "hour": 12, "day": 1}
    tick_all_present(w, {"mara", "player"})
    e = w.entity_states["mara"]
    assert e.last_seen_turn == 5
    assert e.last_seen_location == "tavern"


def test_story_packet_npc_surface_includes_energy_mood() -> None:
    w = _world()
    w.entity_states["mara"] = EntityState(name="mara", energy=0.6, mood="neutral")
    pkt = build_story_packet(w)
    mara_surface = pkt["npc_surface"]["mara"]
    assert "energy" in mara_surface
    assert "mood" in mara_surface
    assert "life_state" in mara_surface
    assert mara_surface["energy"] == 0.6


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
