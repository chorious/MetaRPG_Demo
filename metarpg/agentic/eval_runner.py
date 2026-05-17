"""Eval runner for agentic turns.

Usage:
    python -m metarpg.agentic.eval_runner --case evals/cases/greyfen_beer_loop.json --mock
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from metarpg.agentic.schemas import (
    AuditIssue,
    CandidatePatchEffect,
    NarrativeClaim,
    RewriteTask,
    Segment,
    StoryPacket,
    TurnDraft,
    WriterOutput,
)
from metarpg.agentic.scorecard import TurnScorecard


def load_eval_case(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_mock_story_packet(case: dict[str, Any]) -> StoryPacket:
    return StoryPacket(
        scene={
            "location": "tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": ["ale_mug", "bar_counter"],
            "atmosphere": "quiet, tense tavern",
        },
        player_context={
            "known_facts": ["old_mine_is_sealed"],
            "recent_events": ["player_ordered_ale_from_mara"],
            "inventory_or_handheld": ["ale"],
        },
        npc_surface={
            "mara": {
                "role": "tavern keeper",
                "visible_mood": ["cautious", "reserved"],
                "can_speak": True,
            }
        },
        allowed_effect_kinds=[
            "transient_event",
            "journal_note",
            "observe_reaction",
            "relation_delta",
            "consume_item",
        ],
        allowed_reveals=["old_mine_is_sealed"],
        forbidden={
            "entities_not_present": ["rusk"],
            "hidden_fact_aliases": ["secret_mine_entrance"],
            "forbidden_narration": [
                "npc_inner_thought_hidden_fact",
                "remote_action",
            ],
        },
        hidden_truths=[
            {"fact": "secret_mine_entrance_exists", "alias": "secret_mine_entrance"}
        ],
        full_world_ref="greyfen_default_tavern",
    )


def run_mock_turn(case: dict[str, Any], run_id: str, turn_idx: int) -> TurnDraft:
    draft = TurnDraft(
        draft_id=f"{run_id}_turn_{turn_idx:03d}",
        player_input=case["player_input"],
        pre_world_ref=case.get("initial_session", ""),
    )

    # 1. Story packet
    draft.story_packet = build_mock_story_packet(case)

    # 2. Mock writer output
    draft.writer_output = WriterOutput(
        interpretation=case.get("expected_interpretation", ""),
        segments=[
            Segment(
                id="s1",
                type="player_action",
                text="你仰头喝干杯中的麦酒，苦味在喉间散开。",
                patch_refs=["consume_item:ale"],
                declared_claims=["player_has_or_holds:ale"],
            ),
            Segment(
                id="s2",
                type="npc_observable_reaction",
                text="玛拉瞥了你一眼，又继续擦杯子。",
                patch_refs=["observe_reaction:mara:brief_notice"],
                declared_claims=["same_location:player:mara"],
            ),
        ],
        candidate_patch=[
            CandidatePatchEffect(kind="consume_item", args={"item": "ale"}),
            CandidatePatchEffect(
                kind="observe_reaction", args={"target": "mara", "reaction": "brief_notice"}
            ),
        ],
        assumptions=[
            {
                "claim": "player_has_or_holds:ale",
                "basis": "recent event player_ordered_ale_from_mara",
            }
        ],
    )

    # 3. Mock translator claims
    draft.translated_claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="player_action",
            subject="player",
            action="drink",
            target="ale",
            evidence_span="你仰头喝干杯中的麦酒",
            confidence=0.95,
        ),
        NarrativeClaim(
            segment_id="s2",
            kind="npc_observable_action",
            subject="mara",
            action="glance",
            target="player",
            evidence_span="玛拉瞥了你一眼",
            confidence=0.88,
        ),
    ]

    # 4. Mock deterministic scan
    draft.deterministic_scan = {
        "known_entity_hits": ["player", "mara", "ale"],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
    }

    # 5. Mock hard audit
    draft.hard_audit = {
        "passed": True,
        "issues": [],
        "alignment_check": {
            "narrative_claims_count": 2,
            "patch_effects_count": 2,
            "claims_without_patch_support": 0,
            "patch_without_narrative_support": 0,
        },
    }

    # 6. Mock soft audit
    draft.soft_audit = {
        "passed": True,
        "issues": [],
    }

    # 7. No rewrite needed
    draft.editor_tasks = []
    draft.rewrite_history = []
    draft.final_segments = list(draft.writer_output.segments)
    draft.candidate_patch = list(draft.writer_output.candidate_patch)
    draft.admitted_patch = list(draft.writer_output.candidate_patch)

    # 8. Post-world ref
    draft.post_world_ref = f"{draft.pre_world_ref}_after_turn_{turn_idx}"
    draft.player_output = "\n".join(s.text for s in draft.final_segments)

    return draft


def score_turn(draft: TurnDraft, case: dict[str, Any]) -> TurnScorecard:
    sc = TurnScorecard(turn_id=draft.draft_id)

    # Hard failures from hard audit
    for issue in draft.hard_audit.get("issues", []):
        if issue.get("severity") == "hard_fail":
            sc.hard_failures.append(issue.get("type", "unknown"))

    # Check hidden fact leaks
    for claim in draft.translated_claims:
        if claim.kind == "hidden_fact_reference":
            sc.hidden_leak_count += 1
            sc.hard_failures.append("hidden_fact_leak")

    # Check absent entity actions
    for claim in draft.translated_claims:
        if claim.kind == "remote_event":
            sc.absent_entity_action_count += 1
            sc.hard_failures.append("absent_entity_action")

    # Check raw event exposure
    raw_count = draft.deterministic_scan.get("raw_event_id_hits", [])
    sc.raw_debug_exposure_count = len(raw_count)
    if sc.raw_debug_exposure_count > 0:
        sc.hard_failures.append("raw_debug_exposure")

    # Patch alignment
    alignment = draft.hard_audit.get("alignment_check", {})
    total = max(alignment.get("narrative_claims_count", 1), 1)
    bad = alignment.get("claims_without_patch_support", 0) + alignment.get(
        "patch_without_narrative_support", 0
    )
    sc.patch_alignment_score = max(0.0, 1.0 - (bad / total))

    # Action understanding
    sc.action_understanding_score = 1.0 if draft.writer_output and draft.writer_output.interpretation else 0.0

    # Repair rounds
    sc.repair_rounds = len(draft.rewrite_history)
    sc.rewrite_locality_score = 1.0 if sc.repair_rounds == 0 else 0.5

    # Player experience (mock)
    sc.player_experience_score = 1.0 if not sc.hard_failures else 0.0

    # Grounding
    sc.grounding_score = 1.0 if not sc.hard_failures else 0.0

    # Must / must-not effect kinds
    admitted_kinds = {e.kind for e in draft.admitted_patch}
    for k in case.get("must_include_effect_kinds", []):
        if k not in admitted_kinds:
            sc.notes.append(f"Missing required effect kind: {k}")
            sc.grounding_score = 0.0
    for k in case.get("must_not_include_effect_kinds", []):
        if k in admitted_kinds:
            sc.notes.append(f"Forbidden effect kind present: {k}")
            sc.hard_failures.append("forbidden_effect_kind")

    # Forbidden text
    output_lower = draft.player_output.lower()
    for text in case.get("forbidden_text", []):
        if text.lower() in output_lower:
            sc.notes.append(f"Forbidden text in output: {text}")
            sc.hard_failures.append("forbidden_text")

    return sc


def main() -> int:
    # Force UTF-8 on Windows console
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="Agentic eval runner")
    parser.add_argument("--case", required=True, help="Path to eval case JSON")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no LLM)")
    parser.add_argument("--run-id", default="", help="Run ID (default: UUID)")
    args = parser.parse_args()

    case = load_eval_case(args.case)
    run_id = args.run_id or f"run_{uuid.uuid4().hex[:8]}"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Eval run: {run_id}")
    print(f"Case: {case['id']}")
    print(f"Player input: {case['player_input']}")

    start = time.time()

    if not args.mock:
        print("Non-mock mode not yet implemented in Phase A.")
        return 1

    draft = run_mock_turn(case, run_id, turn_idx=0)
    score = score_turn(draft, case)

    # Write turn draft
    turn_path = run_dir / "turn_000.json"
    with open(turn_path, "w", encoding="utf-8") as f:
        json.dump(draft.to_json(), f, ensure_ascii=False, indent=2)
    print(f"Turn draft written: {turn_path}")

    # Write scorecard
    score_path = run_dir / "scorecard.json"
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(score.to_json(), f, ensure_ascii=False, indent=2)
    print(f"Scorecard written: {score_path}")

    elapsed = int((time.time() - start) * 1000)
    score.latency_ms = elapsed

    print(f"Latency: {elapsed}ms")
    print(f"Acceptable: {score.is_acceptable()}")
    print(f"Hard failures: {score.hard_failures}")
    print(f"Notes: {score.notes}")

    return 0 if score.is_acceptable() else 1


if __name__ == "__main__":
    sys.exit(main())
