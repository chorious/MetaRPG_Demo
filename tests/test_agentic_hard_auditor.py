"""Tests for hard auditor (Phase E)."""
from __future__ import annotations

from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    NarrativeClaim,
    Segment,
)
from metarpg.models import Fact, WorldState


def _base_story_packet():
    return {
        "current_scene": {
            "location": "tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": ["ale_mug"],
        },
        "player_context": {"known_facts": [], "recent_events": [], "inventory_or_handheld": ["ale"]},
        "interaction_context": {"active_hooks": [], "npc_surface_state": {"mara": ["cautious"]}},
        "allowed_effect_kinds": ["consume_item", "observe_reaction", "transient_event"],
        "forbidden": {
            "entities_not_present": ["rusk"],
            "hidden_fact_aliases": ["secret_mine_entrance"],
        },
    }


def _base_world():
    w = WorldState()
    w.npcs = {"mara", "rusk"}
    w.locations = {"tavern", "guard_post"}
    w.facts.add(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("at", ("mara", "tavern")))
    w.facts.add(Fact("has", ("player", "ale")))
    return w


def test_absent_rusk_action_fails():
    pkt = _base_story_packet()
    world = _base_world()
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="npc_observable_action",
            subject="rusk",
            action="nod",
            evidence_span="拉斯克点了点头",
        )
    ]
    result = run_hard_audit(pkt, [], claims, {}, [], world)
    assert not result["passed"]
    types = [i["type"] for i in result["issues"]]
    assert "absent_entity_action" in types


def test_hidden_mine_entrance_leak_fails():
    pkt = _base_story_packet()
    world = _base_world()
    scanner = {"hidden_fact_alias_hits": ["secret_mine_entrance"]}
    result = run_hard_audit(pkt, [], [], scanner, [], world)
    assert not result["passed"]
    types = [i["type"] for i in result["issues"]]
    assert "hidden_fact_leak" in types


def test_drink_without_consume_patch_fails_alignment():
    pkt = _base_story_packet()
    world = _base_world()
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="player_action",
            subject="player",
            action="drink",
            evidence_span="你仰头喝干杯中的麦酒",
        )
    ]
    # No patch effects
    result = run_hard_audit(pkt, [], claims, {}, [], world)
    # Should flag that claim implies state change but no patch supports it
    types = [i["type"] for i in result["issues"]]
    assert "patch_without_support" in types


def test_consume_ale_with_possession_passes():
    pkt = _base_story_packet()
    world = _base_world()
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="player_action",
            subject="player",
            action="drink",
            evidence_span="你仰头喝干杯中的麦酒",
        )
    ]
    result = run_hard_audit(pkt, [], claims, {}, patch, world)
    types = [i["type"] for i in result["issues"]]
    assert "state_change_without_support" not in types
