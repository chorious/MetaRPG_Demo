"""Temporal primitive: time tick + wrap for MetaRPG.

Each player action advances world_time by a default 30 minutes.
Hour wraps to next day. turn counter increments.

Per v0.6.6 review: time is not a cosmetic detail. LLM sees it,
and NPC states must reflect it.
"""
from __future__ import annotations


_DEFAULT_ELAPSED = 30  # minutes per turn


def advance_time(world, elapsed_minutes: int = _DEFAULT_ELAPSED) -> None:
    """Push world_time forward. Wrap hour to next day when crossing 24.

    Args:
        world: a WorldState-like object with a `world_time` dict.
        elapsed_minutes: minutes consumed by this turn (default 30).
    """
    world.world_time["turn"] += 1
    world.world_time["hour"] += elapsed_minutes // 60
    if world.world_time["hour"] >= 24:
        world.world_time["hour"] %= 24
        world.world_time["day"] += 1


def current_time_str(world) -> str:
    """Human-readable time label for story_packet."""
    wt = world.world_time
    hour = wt.get("hour", 12)
    day = wt.get("day", 1)
    turn = wt.get("turn", 0)
    return f"{hour:02d}:00, 第 {day} 天 (turn {turn})"


def time_of_day_mood(hour: int) -> str:
    """Vibe label for a given hour. Used by writer prompt and tests."""
    if 5 <= hour < 9:
        return "early_morning"
    elif 9 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 21:
        return "evening"
    elif 21 <= hour < 24:
        return "night"
    else:
        return "late_night"
