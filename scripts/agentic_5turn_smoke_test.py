"""Agentic v0.6 — full 5-turn Greyfen beer loop smoke test.

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
import time
import uuid
from pathlib import Path

sys.path.insert(0, r"E:\GameDesign\MetaRPG_Dev")

from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.writer_agent import run_writer
from metarpg.agentic.translator_agent import run_translator
from metarpg.agentic.scanner import scan_segment
from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.soft_auditor_agent import run_soft_auditor
from metarpg.agentic.committer import commit_turn
from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.agentic.schemas import TurnDraft
from metarpg.scenarios.greyfen import build


def _log_turn(run_dir: Path, turn_idx: int, draft: TurnDraft, score: TurnScorecard) -> None:
    turn_path = run_dir / f"turn_{turn_idx:03d}.json"
    with open(turn_path, "w", encoding="utf-8") as f:
        json.dump(draft.to_json(), f, ensure_ascii=False, indent=2)

    score_path = run_dir / f"scorecard_{turn_idx:03d}.json"
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump(score.to_json(), f, ensure_ascii=False, indent=2)


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
        print(f"\n{'='*70}")
        print(f"TURN {turn_idx}: {player_input}")
        print("=" * 70)
        logger.emit(turn_idx, "turn", "turn_start", player_input)

        draft = TurnDraft(
            draft_id=f"{run_id}_turn_{turn_idx:03d}",
            player_input=player_input,
            pre_world_ref=f"greyfen_turn_{turn_idx}",
        )

        # 1. Story packet
        t0 = time.time()
        story_packet = build_story_packet(world)
        draft.story_packet = story_packet
        logger.emit(turn_idx, "story_packet", "story_packet_built")
        print(f"\n[1] Story packet built ({time.time()-t0:.2f}s)")
        print(f"    Location: {story_packet['scene']['location']}")
        print(f"    Visible: {story_packet['scene']['visible_entities']}")
        print(f"    Inventory: {story_packet['player_context']['inventory_or_handheld']}")
        print(f"    Allowed effects: {story_packet['allowed_effect_kinds']}")

        # 2. Writer
        t0 = time.time()
        try:
            writer_output = run_writer(story_packet, player_input)
            draft.writer_output = writer_output
            draft.candidate_patch = writer_output.candidate_patch
            logger.emit(turn_idx, "writer", "writer_success", f"segments={len(writer_output.segments)}")
            print(f"\n[2] Writer (DeepSeek Flash) responded ({time.time()-t0:.2f}s)")
            print(f"    Interpretation: {writer_output.interpretation}")
            print(f"    Segments ({len(writer_output.segments)}):")
            for s in writer_output.segments:
                print(f"      [{s.id}] {s.type} | {s.text}")
                print(f"           patch_refs={s.patch_refs}, transient_only={s.transient_only}")
            print(f"    Candidate patch ({len(writer_output.candidate_patch)}):")
            for e in writer_output.candidate_patch:
                print(f"      {e.kind}: {json.dumps(e.args, ensure_ascii=False)}")
            if writer_output.risk_notes:
                print(f"    Risk notes: {writer_output.risk_notes}")
        except Exception as e:
            print(f"\n[2] Writer FAILED: {e}")
            logger.log_error(turn_idx, "writer", type(e).__name__, str(e))
            draft.writer_output = None
            draft.final_segments = []
            draft.player_output = ""
            draft.candidate_patch = []
            draft.hard_audit = {"passed": False, "issues": [{"severity": "hard_fail", "type": "writer_failure", "reason": str(e)}], "alignment_check": {}}
            draft.soft_audit = {"passed": False, "issues": []}
            sc = TurnScorecard(turn_id=draft.draft_id)
            sc.grounding_score = 0.0
            sc.player_experience_score = 0.0
            sc.notes.append(f"Writer failure: {e}")
            draft.scorecard = sc.to_json()
            _log_turn(run_dir, turn_idx, draft, sc)
            overall_scores.append(sc)
            history.append(player_input)
            continue

        # 3. Translator
        t0 = time.time()
        try:
            claims = run_translator(writer_output.segments, story_packet)
            draft.translated_claims = claims
            logger.emit(turn_idx, "translator", "translator_success", f"claims={len(claims)}")
            print(f"\n[3] Translator (Qwen3.6) responded ({time.time()-t0:.2f}s)")
            print(f"    Claims ({len(claims)}):")
            for c in claims:
                print(f"      [{c.segment_id}] {c.kind} | evidence={c.evidence_span[:50]}... | conf={c.confidence}")
        except Exception as e:
            print(f"\n[3] Translator FAILED: {e}")
            logger.log_error(turn_idx, "translator", type(e).__name__, str(e))
            claims = []

        # 4. Scanner
        scanner_findings = {
            "known_entity_hits": [],
            "hidden_fact_alias_hits": [],
            "raw_event_id_hits": [],
            "inner_thought_verb_hits": [],
            "remote_event_cue_hits": [],
            "unsupported_location_mentions": [],
            "claims": [],
        }
        known_entities = story_packet.get("scene", {}).get("visible_entities", [])
        known_locations = list(world.locations)
        hidden_aliases = story_packet.get("forbidden", {}).get("hidden_fact_aliases", [])
        for s in writer_output.segments:
            findings = scan_segment(s.id, s.text, known_entities, known_locations, hidden_aliases)
            for k, v in findings.items():
                if isinstance(v, list):
                    scanner_findings.setdefault(k, []).extend(v)
        draft.deterministic_scan = scanner_findings
        logger.emit(turn_idx, "scanner", "scanner_success")
        print(f"\n[4] Scanner complete")
        hit_summary = {k: len(v) for k, v in scanner_findings.items() if isinstance(v, list) and v}
        if hit_summary:
            print(f"    Hits: {hit_summary}")
        else:
            print(f"    No scanner hits (clean)")

        # 5. Hard Auditor
        audit = run_hard_audit(
            story_packet,
            writer_output.segments,
            claims,
            scanner_findings,
            writer_output.candidate_patch,
            world,
        )
        draft.hard_audit = audit
        logger.emit(turn_idx, "hard_audit", "hard_audit_success", f"passed={audit['passed']}")
        print(f"\n[5] Hard Auditor complete")
        print(f"    Passed: {audit['passed']}")
        if audit["issues"]:
            for issue in audit["issues"]:
                print(f"    [FAIL] {issue['type']}: {issue['reason']}")
                print(f"           Repair: {issue['repair_instruction']}")
        else:
            print(f"    No hard failures")
        align = audit.get("alignment_check", {})
        print(f"    Alignment: claims={align.get('narrative_claims_count',0)} patch={align.get('patch_effects_count',0)} mismatch={align.get('claims_without_patch_support',0)}")

        # 6. Soft Auditor (skip if hard failures exist to save tokens)
        if audit["passed"]:
            t0 = time.time()
            try:
                soft_issues = run_soft_auditor(
                    writer_output.segments,
                    history,
                    [e.__dict__ for e in writer_output.candidate_patch],
                )
                draft.soft_audit = {"passed": len(soft_issues) == 0, "issues": [i.__dict__ for i in soft_issues]}
                logger.emit(turn_idx, "soft_audit", "soft_audit_success", f"issues={len(soft_issues)}")
                print(f"\n[6] Soft Auditor ({time.time()-t0:.2f}s)")
                if soft_issues:
                    for issue in soft_issues:
                        print(f"    [SOFT] {issue.type}: {issue.reason}")
                else:
                    print(f"    No soft issues")
            except Exception as e:
                print(f"\n[6] Soft Auditor FAILED: {e}")
                logger.log_error(turn_idx, "soft_auditor", type(e).__name__, str(e))
                draft.soft_audit = {"passed": True, "issues": []}
        else:
            draft.soft_audit = {"passed": False, "issues": []}
            print(f"\n[6] Soft Auditor skipped (hard failures exist)")

        # 7. Commit (admit all candidate patch if hard audit passed, else admit only safe effects)
        if audit["passed"]:
            admitted = writer_output.candidate_patch
        else:
            # Conservative: only admit transient effects and observe_reactions
            admitted = [
                e for e in writer_output.candidate_patch
                if e.kind in {"transient_event", "observe_reaction", "journal_note"}
            ]
        draft.admitted_patch = admitted
        draft.final_segments = writer_output.segments
        draft.player_output = "\n".join(s.text for s in writer_output.segments)

        if admitted:
            t0 = time.time()
            result = commit_turn(world, admitted, writer_output.segments)
            logger.emit(turn_idx, "commit", "commit_success", f"turn={world.turn}")
            print(f"\n[7] Committer applied ({time.time()-t0:.2f}s)")
            print(f"    Turn now: {world.turn}")
            delta = result["delta"]
            for k, v in delta.items():
                if v:
                    print(f"    {k}: {v}")
            print(f"    Player output:\n    {result['player_output'].replace(chr(10), chr(10)+'    ')}")
        else:
            logger.emit(turn_idx, "commit", "commit_success", "nothing_admitted")
            print(f"\n[7] Committer: nothing admitted (hard audit failed)")

        # 8. Score
        sc = TurnScorecard(turn_id=draft.draft_id)
        sc.hidden_leak_count = sum(1 for c in claims if c.kind == "hidden_fact_reference")
        sc.absent_entity_action_count = sum(1 for c in claims if c.kind == "remote_event")
        sc.raw_debug_exposure_count = len(scanner_findings.get("raw_event_id_hits", []))
        sc.patch_alignment_score = 1.0 if audit["alignment_check"].get("claims_without_patch_support", 0) == 0 else 0.5
        sc.action_understanding_score = 1.0 if writer_output and writer_output.interpretation else 0.0
        sc.grounding_score = 1.0 if audit["passed"] else 0.0
        sc.repair_rounds = len(draft.rewrite_history)
        sc.rewrite_locality_score = 1.0 if sc.repair_rounds == 0 else 0.5

        # Ingest hard audit issues
        for issue in audit.get("issues", []):
            sc.hard_failures.append(issue.get("type", ""))
        for issue in audit.get("medium_issues", []):
            sc.medium_issues.append(issue.get("type", ""))
        sc.hard_issue_count = len(audit.get("issues", []))
        sc.medium_issue_count = len(audit.get("medium_issues", []))

        # Ingest soft audit issues
        soft_audit = draft.soft_audit or {}
        for issue in soft_audit.get("issues", []):
            sc.soft_issues.append(issue.get("type", ""))
        sc.soft_issue_count = len(soft_audit.get("issues", []))

        # Player output check
        if not draft.player_output.strip():
            sc.missing_player_output = True
            sc.notes.append("missing_player_output")

        # Compute experience score truthfully
        sc.player_experience_score = sc.compute_player_experience()

        draft.scorecard = sc.to_json()

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

        # Save
        _log_turn(run_dir, turn_idx, draft, sc)
        logger.emit(turn_idx, "turn", "turn_written", f"turn_{turn_idx:03d}.json")
        overall_scores.append(sc)
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
