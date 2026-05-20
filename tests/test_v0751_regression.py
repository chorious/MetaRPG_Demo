"""v0.7.5.1 regression tests for review findings."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from metarpg.agentic.post_render_checker import check_rendered_prose
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    RenderBrief,
    TurnTransaction,
)
from metarpg.agentic.transaction_validator import validate_transaction
from metarpg.models import Fact, WorldState


# ---------------------------------------------------------------------------
# Fix 1 — L2 judge fail-closed on call failure
# ---------------------------------------------------------------------------


class FailingJudgeClient:
    """Mock client that always raises on chat_json."""

    def chat_json(self, messages, temperature=0.0):
        raise RuntimeError("vLLM timeout")


class PassingJudgeClient:
    """Mock client that returns a pass judgment."""

    def chat_json(self, messages, temperature=0.0):
        return {
            "verdict": "pass",
            "category": "mock",
            "evidence": "mock pass",
            "confidence": 0.9,
        }


def _make_l2_required_tx() -> TurnTransaction:
    """Build a transaction that triggers L2 required (speak op)."""
    return TurnTransaction(
        id="test",
        player_input="test",
        player_intent={},
        narrative_frame=NarrativeFrame(
            beat="",
            active_hooks=[],
            candidate_hints=[],
            motifs_to_use=[],
            dramatic_function="",
            allowed_commitment_levels=[],
            forbidden_moves=[],
            resolved_targets=[],
            resolved_props=[],
            unresolved_mentions=[],
            canonical_id_whitelist={"visible_entity_ids": ["mara"]},
            semantic_judgments=[],
        ),
        operations=[Operation(kind="speak", params={"entity": "mara"})],
        commitments=[],
        render_brief=RenderBrief(
            committed_events=[],
            visible_reactions=[],
            allowed_hints=[],
            motifs_to_render=[],
            style_constraints=[],
            forbidden_claims=[],
            player_location="",
            visible_entities=["mara"],
            visible_objects=[],
            absent_entities=[],
            current_turn_obligation={},
        ),
        forbidden_claims=[],
        assumptions=[],
    )


def test_l2_required_judge_failure_fail_closed():
    """When client raises on an L2-required turn, status must be failed."""
    tx = _make_l2_required_tx()
    world = WorldState(facts=[], locations=[])
    result = check_rendered_prose("test prose", tx, world, client=FailingJudgeClient())
    assert result["status"] == "failed"
    assert any("semantic judge failed" in iss for iss in result["issues"])


def test_l2_required_judge_pass_with_working_client():
    """Sanity: working client still passes when no real violations."""
    tx = _make_l2_required_tx()
    world = WorldState(facts=[], locations=[])
    result = check_rendered_prose("test prose", tx, world, client=PassingJudgeClient())
    assert result["status"] == "pass"


# ---------------------------------------------------------------------------
# Fix 2 — Play artifact / analyzer contract alignment
# ---------------------------------------------------------------------------


def test_analyze_play_reads_semantic_judgments_from_post_render():
    """_extract_semantic_judgments reads from nested post_render dict."""
    from scripts.analyze_play_run import _extract_semantic_judgments

    turn = {
        "post_render": {
            "semantic_judgments": [
                {"check": "intent_fulfillment", "verdict": "reject"}
            ]
        }
    }
    sjs = _extract_semantic_judgments(turn)
    assert len(sjs) == 1
    assert sjs[0]["verdict"] == "reject"


def test_analyze_play_reads_hidden_truths_from_world():
    """_extract_hidden_truths reads from world.hidden_truths."""
    from scripts.analyze_play_run import _extract_hidden_truths

    turn = {
        "world": {
            "hidden_truths": [
                {"predicate": "at", "args": ["rusk", "guard_post"], "alias": "rusk_at_guard_post"}
            ]
        }
    }
    hts = _extract_hidden_truths(turn)
    assert "at(rusk, guard_post)" in hts
    assert "rusk_at_guard_post" in hts


def test_analyze_play_reads_public_facts_from_world_facts():
    """_extract_public_facts reads from world.facts."""
    from scripts.analyze_play_run import _extract_public_facts

    turn = {
        "world": {"facts": ["has(player, ale)", "at(player, tavern)"]},
        "player_output": "你喝了一口麦酒。",
    }
    facts = _extract_public_facts(turn)
    assert "has(player, ale)" in facts
    assert "at(player, tavern)" in facts
    assert "你喝了一口麦酒。" in facts


# ---------------------------------------------------------------------------
# Fix 3 — Analyzer l2_required reconstruction
# ---------------------------------------------------------------------------


def test_analyzer_reconstructs_l2_required_for_unreachable():
    """Analyzer marks l2_required=True when render_brief has unreachable response_mode."""
    from scripts.analyze_agentic_run import _analyze_turn

    # Build a minimal artifact set with render_brief indicating unreachable
    tmp = Path(__file__).parent / "tmp_test_artifacts"
    tmp.mkdir(exist_ok=True)

    render_brief = {
        "current_turn_obligation": {"response_mode": "unreachable", "must_not_claim": []}
    }
    narrative_frame = {"candidate_hints": []}
    transaction_raw = {"parsed": {"operations": [], "commitments": [], "assumptions": [], "forbidden_claims": []}}
    resolved_intent = {"targets": []}

    (tmp / "artifact_001_render_brief.json").write_text(json.dumps(render_brief), encoding="utf-8")
    (tmp / "artifact_001_narrative_frame.json").write_text(json.dumps(narrative_frame), encoding="utf-8")
    (tmp / "artifact_001_transaction_raw.json").write_text(json.dumps(transaction_raw), encoding="utf-8")
    (tmp / "artifact_001_resolved_intent.json").write_text(json.dumps(resolved_intent), encoding="utf-8")

    artifacts = {
        "render_brief": tmp / "artifact_001_render_brief.json",
        "narrative_frame": tmp / "artifact_001_narrative_frame.json",
        "transaction_raw": tmp / "artifact_001_transaction_raw.json",
        "resolved_intent": tmp / "artifact_001_resolved_intent.json",
    }
    result = _analyze_turn(1, artifacts)
    assert result["l2_required"] is True

    # cleanup
    for p in tmp.glob("*"):
        p.unlink()
    tmp.rmdir()


def test_analyzer_reconstructs_l2_required_for_symbolic_risk_hint():
    """Analyzer marks l2_required=True when candidate_hints contain symbolic risk."""
    from scripts.analyze_agentic_run import _analyze_turn

    tmp = Path(__file__).parent / "tmp_test_artifacts"
    tmp.mkdir(exist_ok=True)

    narrative_frame = {"candidate_hints": ["the hidden password"]}
    transaction_raw = {"parsed": {"operations": [], "commitments": [], "assumptions": [], "forbidden_claims": []}}
    resolved_intent = {"targets": []}

    (tmp / "artifact_001_narrative_frame.json").write_text(json.dumps(narrative_frame), encoding="utf-8")
    (tmp / "artifact_001_transaction_raw.json").write_text(json.dumps(transaction_raw), encoding="utf-8")
    (tmp / "artifact_001_resolved_intent.json").write_text(json.dumps(resolved_intent), encoding="utf-8")

    artifacts = {
        "narrative_frame": tmp / "artifact_001_narrative_frame.json",
        "transaction_raw": tmp / "artifact_001_transaction_raw.json",
        "resolved_intent": tmp / "artifact_001_resolved_intent.json",
    }
    result = _analyze_turn(1, artifacts)
    assert result["l2_required"] is True

    for p in tmp.glob("*"):
        p.unlink()
    tmp.rmdir()


# ---------------------------------------------------------------------------
# Fix 4 — Restore missing-whitelist fallback behavior
# ---------------------------------------------------------------------------


def _make_world_with_mara() -> WorldState:
    return WorldState(
        facts=[Fact(predicate="at", args=["mara", "tavern"])],
        locations=["tavern"],
    )


def test_validator_missing_whitelist_fallback_to_world():
    """No canonical_id_whitelist -> fallback to world presence; speak to present NPC passes."""
    world = _make_world_with_mara()
    tx = TurnTransaction(
        id="test",
        player_input="test",
        player_intent={},
        narrative_frame=NarrativeFrame(
            beat="",
            active_hooks=[],
            candidate_hints=[],
            motifs_to_use=[],
            dramatic_function="",
            allowed_commitment_levels=[],
            forbidden_moves=[],
            resolved_targets=[],
            resolved_props=[],
            unresolved_mentions=[],
            canonical_id_whitelist={},  # empty dict, no visible_entity_ids key
            semantic_judgments=[],
        ),
        operations=[Operation(kind="speak", params={"entity": "mara"})],
        commitments=[],
        render_brief=RenderBrief(
            committed_events=[],
            visible_reactions=[],
            allowed_hints=[],
            motifs_to_render=[],
            style_constraints=[],
            forbidden_claims=[],
            player_location="",
            visible_entities=[],
            visible_objects=[],
            absent_entities=[],
            current_turn_obligation={},
        ),
        forbidden_claims=[],
        assumptions=[],
    )
    result = validate_transaction(tx, world)
    # No hard_fail because missing whitelist falls back to world presence
    hard_fails = [i for i in result.issues if i.severity == "hard_fail"]
    assert len(hard_fails) == 0


def test_validator_empty_whitelist_is_strict():
    """Explicit empty visible_entity_ids -> only player/environment visible."""
    world = _make_world_with_mara()
    tx = TurnTransaction(
        id="test",
        player_input="test",
        player_intent={},
        narrative_frame=NarrativeFrame(
            beat="",
            active_hooks=[],
            candidate_hints=[],
            motifs_to_use=[],
            dramatic_function="",
            allowed_commitment_levels=[],
            forbidden_moves=[],
            resolved_targets=[],
            resolved_props=[],
            unresolved_mentions=[],
            canonical_id_whitelist={"visible_entity_ids": []},
            semantic_judgments=[],
        ),
        operations=[Operation(kind="speak", params={"entity": "mara"})],
        commitments=[],
        render_brief=RenderBrief(
            committed_events=[],
            visible_reactions=[],
            allowed_hints=[],
            motifs_to_render=[],
            style_constraints=[],
            forbidden_claims=[],
            player_location="",
            visible_entities=[],
            visible_objects=[],
            absent_entities=[],
            current_turn_obligation={},
        ),
        forbidden_claims=[],
        assumptions=[],
    )
    result = validate_transaction(tx, world)
    hard_fails = [i for i in result.issues if i.severity == "hard_fail"]
    assert len(hard_fails) == 1
    assert hard_fails[0].type == "absent_entity"
