"""Tests for time_flow primitive (v0.6.6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.time_flow import advance_time, current_time_str, time_of_day_mood
from metarpg.models import Fact, WorldState


def _world(hour: int = 12, day: int = 1, turn: int = 0) -> WorldState:
    w = WorldState()
    w.world_time = {"turn": turn, "hour": hour, "day": day}
    return w


def test_advance_time_default_30min() -> None:
    w = _world(hour=12, day=1, turn=0)
    advance_time(w)
    assert w.world_time["turn"] == 1
    assert w.world_time["hour"] == 12
    assert w.world_time["day"] == 1


def test_advance_time_wraps_day() -> None:
    """23:00 + 2h = 01:00 next day."""
    w = _world(hour=23, day=3, turn=10)
    advance_time(w, elapsed_minutes=120)
    assert w.world_time["hour"] == 1
    assert w.world_time["day"] == 4
    assert w.world_time["turn"] == 11


def test_advance_time_multiple_days() -> None:
    """22:00 + 6h = 04:00 next day."""
    w = _world(hour=22, day=1, turn=0)
    advance_time(w, elapsed_minutes=360)
    assert w.world_time["hour"] == 4
    assert w.world_time["day"] == 2


def test_time_of_day_mood_coverage() -> None:
    assert time_of_day_mood(6) == "early_morning"
    assert time_of_day_mood(10) == "morning"
    assert time_of_day_mood(12) == "noon"
    assert time_of_day_mood(15) == "afternoon"
    assert time_of_day_mood(19) == "evening"
    assert time_of_day_mood(22) == "night"
    assert time_of_day_mood(2) == "late_night"


def test_current_time_str_includes_hour_and_day() -> None:
    w = _world(hour=17, day=3, turn=5)
    s = current_time_str(w)
    assert "17" in s
    assert "3" in s
    assert "5" in s


def test_story_packet_exposes_current_time() -> None:
    w = _world(hour=17, day=2, turn=4)
    # Add minimal facts so build_story_packet doesn't error
    w.facts.add(Fact("at", ("player", "tavern")))
    w.npcs = {"mara"}
    w.facts.add(Fact("at", ("mara", "tavern")))

    pkt = build_story_packet(w)
    ct = pkt["player_context"]["current_time"]
    assert ct is not None and isinstance(ct, str)
    assert "17" in ct  # hour should appear
    assert "2" in ct   # day should appear


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
