"""Hard Auditor consume_item recovery via recent_events.

Verifies that consume_item passes audit when the player does not yet have
a `has(player, X)` fact but a recent_events entry references the item
(e.g. a transient_event from the previous turn that committed the item
into the player's hands without a hard fact update).

This is the Step 1 engine fix: hard_auditor reads recent_events (the
canonical player-context window) instead of the keyword-filtered
inventory_events helper.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.schemas import CandidatePatchEffect
from metarpg.models import Fact, WorldState


def _empty_world() -> WorldState:
    w = WorldState()
    w.npcs = {"mara"}
    w.locations = {"tavern"}
    w.facts.add(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("at", ("mara", "tavern")))
    return w


def _packet(recent_events: list[str]) -> dict:
    return {
        "scene": {
            "location": "tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": [],
        },
        "player_context": {
            "known_facts": [],
            "recent_events": recent_events,
            "inventory_or_handheld": [],
        },
        "allowed_effect_kinds": ["consume_item", "transient_event"],
        "forbidden": {"entities_not_present": [], "hidden_fact_aliases": []},
    }


def test_consume_passes_when_recent_events_mention_item() -> None:
    """A recent transient event mentions 'ale' -> consume_item passes."""
    world = _empty_world()
    pkt = _packet(["Mara poured ale for player"])
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]

    result = run_hard_audit(pkt, [], [], {}, patch, world)
    types = [i["type"] for i in result["issues"]]
    assert "state_change_without_support" not in types


def test_consume_fails_when_recent_events_empty() -> None:
    """No has-fact, no recent_events reference -> hard fail."""
    world = _empty_world()
    pkt = _packet([])  # nothing recent
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]

    result = run_hard_audit(pkt, [], [], {}, patch, world)
    types = [i["type"] for i in result["issues"]]
    assert "state_change_without_support" in types


def test_consume_fails_when_recent_events_mention_different_item() -> None:
    """Recent events mention bread, but consume_item is for ale."""
    world = _empty_world()
    pkt = _packet(["Mara handed bread to player"])
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]

    result = run_hard_audit(pkt, [], [], {}, patch, world)
    types = [i["type"] for i in result["issues"]]
    assert "state_change_without_support" in types


def test_consume_case_insensitive_match() -> None:
    """Recent events match item case-insensitively."""
    world = _empty_world()
    pkt = _packet(["Mara POURED ALE for the customer"])
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]

    result = run_hard_audit(pkt, [], [], {}, patch, world)
    types = [i["type"] for i in result["issues"]]
    assert "state_change_without_support" not in types


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
