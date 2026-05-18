"""Tests for offscreen_tick primitive (v0.6.6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.offscreen_tick import (
    ambient_events_for_scene,
    tick_offscreen_entities,
)
from metarpg.models import EntityState, WorldState


def _world() -> WorldState:
    w = WorldState()
    w.world_time = {"turn": 10, "hour": 12, "day": 1}
    return w


def test_tick_offscreen_entities_updates_energy() -> None:
    w = _world()
    w.entity_states["mara"] = EntityState(name="mara", energy=1.0, last_seen_turn=5)
    desc = tick_offscreen_entities(w, current_turn=10, client=None)
    e = w.entity_states["mara"]
    # 5 turns away: 1.0 - 0.05*5 = 0.75
    assert e.energy == 0.75
    assert "mara" in desc


def test_present_entities_not_ticked() -> None:
    w = _world()
    w.entity_states["mara"] = EntityState(name="mara", energy=1.0, last_seen_turn=9)
    desc = tick_offscreen_entities(w, current_turn=10, client=None)
    # last_seen_turn=9, current_turn=10: 9 >= 10-1 (9) so NOT offscreen
    assert "mara" not in desc
    assert w.entity_states["mara"].energy == 1.0


def test_ambient_events_returns_list() -> None:
    w = _world()
    w.entity_states["rusk"] = EntityState(name="rusk", energy=0.1, last_seen_turn=2)
    events = ambient_events_for_scene(w, current_turn=10)
    assert isinstance(events, list)
    assert len(events) >= 1
    assert any("rusk" in e for e in events)


def test_offscreen_low_energy_description() -> None:
    w = _world()
    w.entity_states["iven"] = EntityState(name="iven", energy=0.1, last_seen_turn=1)
    desc = tick_offscreen_entities(w, current_turn=10, client=None)
    text = desc.get("iven", "")
    assert "exhausted" in text.lower() or "fatigue" in text.lower()


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
