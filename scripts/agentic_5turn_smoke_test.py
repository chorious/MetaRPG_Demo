"""Agentic v0.6.3 — full 5-turn Greyfen beer loop smoke test.

Routes through metarpg.agentic.runner for canonical turn orchestration.
Runs end-to-end with real LLMs, preserving all output logs.

Turns:
1. 要了一杯啤酒
2. 耸了耸肩 "这杯酒真不错"
3. 一饮而尽
4. "这附近发生了什么事情么？我是新来的，嘿嘿"
5. 静静地记下了这条信息
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, r"E:\GameDesign\MetaRPG_Dev")

from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import run_agentic_turn
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.scenarios.greyfen import build


def _print_turn_result(turn_idx: int, result: dict, player_input: str) -> None:
    """Print verbose turn diagnostics."""
    draft = result["draft"]
    sc = result["scorecard"]

    print(f"\n{'='*70}")
    print(f"TURN {turn_idx}: {player_input}")
    print("=" * 70)

    print(f"\n[1] Story packet built")
    sp = draft.story_packet or {}
    print(f"    Location: {sp.get('scene', {}).get('location', '?')}")
    print(f"    Visible: {sp.get('scene', {}).get('visible_entities', [])}")
    print(f"    Inventory: {sp.get('player_context', {}).get('inventory_or_handheld', [])}")

    writer = draft.writer_output
    if writer:
        print(f"\n[2] Writer responded")
        print(f"    Interpretation: {writer.interpretation}")
        print(f"    Segments ({len(writer.segments)}):")
        for s in writer.segments:
            print(f"      [{s.id}] {s.type} | {s.text}")
            print(f"           patch_refs={s.patch_refs}, transient_only={s.transient_only}")
        print(f"    Candidate patch ({len(writer.candidate_patch)}):")
        for e in writer.candidate_patch:
            print(f"      {e.kind}: {json.dumps(e.args, ensure_ascii=False)}")
        if writer.risk_notes:
            print(f"    Risk notes: {writer.risk_notes}")
    else:
        print("\n[2] Writer FAILED")

    claims = draft.translated_claims
    if claims:
        print(f"\n[3] Translator claims ({len(claims)}):")
        for c in claims:
            print(f"      [{c.segment_id}] {c.kind} | evidence={c.evidence_span[:50]}... | conf={c.confidence}")

    scan = draft.deterministic_scan or {}
    hit_summary = {k: len(v) for k, v in scan.items() if isinstance(v, list) and v}
    if hit_summary:
        print(f"\n[4] Scanner hits: {hit_summary}")
    else:
        print("\n[4] Scanner clean")

    audit = draft.hard_audit or {}
    print(f"\n[5] Hard Auditor: passed={audit.get('passed')}")
    for issue in audit.get("issues", []):
        print(f"    [FAIL] {issue['type']}: {issue['reason']}")
    for issue in audit.get("medium_issues", []):
        print(f"    [MED] {issue['type']}: {issue['reason']}")
    align = audit.get("alignment_check", {})
    print(f"    Alignment: claims={align.get('narrative_claims_count',0)} patch={align.get('patch_effects_count',0)} mismatch={align.get('claims_without_patch_support',0)}")

    soft = draft.soft_audit or {}
    soft_issues = soft.get("issues", [])
    if soft_issues:
        print(f"\n[6] Soft issues ({len(soft_issues)}):")
        for issue in soft_issues:
            print(f"    [SOFT] {issue['type']}: {issue['reason']}")
    else:
        print("\n[6] Soft Auditor clean")

    print(f"\n[7] Commit: committed={result['committed']}")

    print(f"\n[8] Scorecard")
    print(f"    Grounding: {sc.grounding_score}")
    print(f"    Patch alignment: {sc.patch_alignment_score}")
    print(f"    Action understanding: {sc.action_understanding_score}")
    print(f"    Hard issues: {sc.hard_issue_count} | Medium: {sc.medium_issue_count} | Soft: {sc.soft_issue_count}")
    print(f"    Player experience: {sc.player_experience_score}")
    print(f"    Acceptable: {sc.is_acceptable()}")
    if sc.notes:
        for note in sc.notes:
            print(f"    Note: {note}")

    print(f"\n    Player output:\n    {result['player_output'].replace(chr(10), chr(10)+'    ')}")


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    run_id = f"smoke_{uuid.uuid4().hex[:8]}"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger = RunLogger(run_id, run_dir)

    world = build()
    history: list[str] = []

    turns = [
        (1, "要了一杯啤酒"),
        (2, "耸了耸肩 \"这杯酒真不错\""),
        (3, "一饮而尽"),
        (4, "\"这附近发生了什么事情么？我是新来的，嘿嘿\""),
        (5, "静静地记下了这条信息"),
    ]

    print("=" * 70)
    print(f"Agentic 5-Turn Smoke Test  RunID: {run_id}")
    print("=" * 70)

    overall_scores: list[TurnScorecard] = []

    for turn_idx, player_input in turns:
        result = run_agentic_turn(
            world=world,
            player_input=player_input,
            turn_index=turn_idx,
            run_id=run_id,
            history=history,
            run_logger=logger,
        )

        _print_turn_result(turn_idx, result, player_input)
        overall_scores.append(result["scorecard"])
        history.append(player_input)

    # Final summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print("=" * 70)
    all_pass = all(sc.is_acceptable() for sc in overall_scores)
    print(f"All turns acceptable: {all_pass}")
    for sc in overall_scores:
        status = "PASS" if sc.is_acceptable() else "FAIL"
        print(f"  {sc.turn_id}: {status} | grounding={sc.grounding_score} | alignment={sc.patch_alignment_score}")
    print(f"\nLogs saved to: {run_dir}")
    print("=" * 70)

    hard_failures = []
    medium_issues = []
    soft_issues = []
    for sc in overall_scores:
        hard_failures.extend(sc.hard_failures)
        medium_issues.extend(sc.medium_issues)
        soft_issues.extend(sc.soft_issues)
    logger.close(
        turns_attempted=len(turns),
        turns_completed=len(overall_scores),
        scorecards=[sc.to_json() for sc in overall_scores],
        hard_failures=hard_failures,
        medium_issues=medium_issues,
        soft_issues=soft_issues,
        case_id="greyfen_beer_loop",
    )

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
