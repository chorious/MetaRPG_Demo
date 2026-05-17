"""v0.6.1 regression cases — deterministic, no LLM required.

Case A: Ambient guests should pass
Case B: Notebook/ink should medium-issue
Case C: NPC offer without patch should hard-fail
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.schemas import CandidatePatchEffect, NarrativeClaim, Segment
from metarpg.models import Fact, WorldState


def _build_world() -> WorldState:
    w = WorldState()
    w.locations = {"greyfen_tavern"}
    w.npcs = {"mara"}
    w.facts.add(Fact("at", ("player", "greyfen_tavern")))
    w.facts.add(Fact("at", ("mara", "greyfen_tavern")))
    return w


def _story_packet() -> dict:
    return {
        "scene": {
            "location": "greyfen_tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": [],
            "atmosphere": "tense greyfen_tavern (tavern, drink)",
        },
        "player_context": {
            "known_facts": [],
            "recent_events": [],
            "inventory_or_handheld": [],
        },
        "npc_surface": {
            "mara": {
                "role": "barkeep",
                "visible_mood": ["neutral"],
                "can_speak": True,
                "_auditor_relations": {},
            }
        },
        "allowed_effect_kinds": [
            "transient_event",
            "journal_note",
            "observe_reaction",
            "relation_delta",
            "consume_item",
            "acquire_item",
            "knowledge_transfer",
            "reveal",
        ],
        "allowed_reveals": [],
        "forbidden": {
            "entities_not_present": ["rusk", "iven"],
            "hidden_fact_aliases": ["mara_at_old_mine", "secret_smuggling_ring"],
            "forbidden_narration": [
                "npc_inner_thought_hidden_fact",
                "remote_action",
                "raw_event_id",
                "belief_probability",
            ],
        },
    }


def case_a_ambient_guests_pass() -> None:
    """Unnamed tavern guests are ambient detail — should pass hard audit."""
    packet = _story_packet()
    segments = [Segment(id="s1", type="narration", text="远处三两桌低声交谈的客人偶尔瞥你一眼。")]
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="ambient_entity_action",
            subject="unnamed_guests",
            evidence_span="远处三两桌低声交谈的客人偶尔瞥你一眼",
            confidence=0.8,
            metadata={"scope": "background"},
        )
    ]
    scanner = {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }
    patch: list[CandidatePatchEffect] = []
    world = _build_world()

    result = run_hard_audit(packet, segments, claims, scanner, patch, world)

    assert result["passed"] is True, f"Case A should pass, got issues: {result['issues']}"
    assert len(result["issues"]) == 0
    print("[PASS] Case A: ambient guests pass")


def case_b_notebook_medium() -> None:
    """Unregistered notebook/ink is medium_issue, not hard_fail."""
    packet = _story_packet()
    segments = [Segment(id="s1", type="player_action", text="你从怀中取出随身携带的笔记本，蘸了蘸墨水，写下这条消息。")]
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="prop_usage",
            subject="player",
            action="write",
            evidence_span="你从怀中取出随身携带的笔记本，蘸了蘸墨水",
            confidence=0.85,
            metadata={"prop": "notebook"},
        )
    ]
    scanner = {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }
    patch: list[CandidatePatchEffect] = []
    world = _build_world()

    result = run_hard_audit(packet, segments, claims, scanner, patch, world)

    # Should NOT hard-fail
    hard_types = {i["type"] for i in result["issues"]}
    assert "state_change_without_support" not in hard_types, "Notebook usage should not hard-fail"

    # Should produce medium_issue
    medium_types = {i["type"] for i in result["medium_issues"]}
    assert "unregistered_concrete_prop" in medium_types, f"Expected medium unregistered_concrete_prop, got medium_issues={result['medium_issues']}"
    print("[PASS] Case B: notebook is medium_issue")


def case_c_npc_offer_fails() -> None:
    """NPC offer without matching patch should hard-fail."""
    packet = _story_packet()
    segments = [Segment(id="s1", type="npc_speech", text="玛拉说：“再来一杯？”")]
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="npc_offer",
            subject="mara",
            action="offer_refill",
            evidence_span="玛拉说：“再来一杯？”",
            confidence=0.95,
            metadata={"offer_type": "drink_refill"},
        )
    ]
    scanner = {
        "known_entity_hits": ["mara"],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }
    # Patch has only observe_reaction, no speech/offer support
    patch = [CandidatePatchEffect(kind="observe_reaction", args={"target": "mara", "reaction": "mild_interest"})]
    world = _build_world()

    result = run_hard_audit(packet, segments, claims, scanner, patch, world)

    assert result["passed"] is False, "Case C should fail hard audit"
    hard_types = {i["type"] for i in result["issues"]}
    assert "npc_offer_without_patch_support" in hard_types or "npc_speech_without_patch_support" in hard_types, (
        f"Expected offer/speech hard fail, got: {result['issues']}"
    )
    print("[PASS] Case C: NPC offer without patch hard-fails")


def test_case_a_ambient_guests_pass() -> None:
    case_a_ambient_guests_pass()


def test_case_b_notebook_medium() -> None:
    case_b_notebook_medium()


def test_case_c_npc_offer_fails() -> None:
    case_c_npc_offer_fails()


if __name__ == "__main__":
    print("=" * 60)
    print("v0.6.1 Regression Cases")
    print("=" * 60)
    case_a_ambient_guests_pass()
    case_b_notebook_medium()
    case_c_npc_offer_fails()
    print("=" * 60)
    print("All regression cases passed.")
    print("=" * 60)
