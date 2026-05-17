"""Agentic v0.6.1 — interactive play CLI.

Usage:
    python scripts/play_agentic.py

Commands:
    <anything else>  Player action or speech
    /look            Show scene summary
    /inv             Show inventory
    /save            Save current world state
    /quit            Exit
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
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


def _clear():
    os.system("cls" if sys.platform == "win32" else "clear")


def _print_scene(packet: dict) -> None:
    scene = packet.get("scene", {})
    ctx = packet.get("player_context", {})
    print(f"\n  [{scene.get('location', '?')}]")
    print(f"  氛围: {scene.get('atmosphere', '')}")
    print(f"  可见: {', '.join(scene.get('visible_entities', []))}")
    inv = ctx.get("inventory_or_handheld", [])
    if inv:
        print(f"  携带: {', '.join(inv)}")
    objs = scene.get("visible_objects", [])
    if objs:
        print(f"  物品: {', '.join(objs)}")
    recent = ctx.get("recent_events", [])
    if recent:
        print(f"  最近: {recent[-1]}")


def _print_output(segments: list) -> None:
    print("\n" + "-" * 50)
    for s in segments:
        print(f"\n{s.text}")
    print("-" * 50)


def _print_audit(audit: dict) -> None:
    if not audit.get("passed"):
        print("\n  [审计未通过]")
        for issue in audit.get("issues", []):
            print(f"    ! {issue['type']}: {issue['reason']}")
    medium = audit.get("medium_issues", [])
    if medium:
        print("\n  [注意]")
        for issue in medium:
            print(f"    ~ {issue['type']}: {issue['reason']}")


def _print_score(sc: TurnScorecard) -> None:
    print(f"\n  [评分] 体验={sc.player_experience_score:.2f}  grounding={sc.grounding_score:.2f}", end="")
    if sc.hard_issue_count:
        print(f"  硬问题={sc.hard_issue_count}", end="")
    if sc.medium_issue_count:
        print(f"  中等问题={sc.medium_issue_count}", end="")
    if sc.soft_issue_count:
        print(f"  软性={sc.soft_issue_count}", end="")
    print()


def _save_world(world, run_dir: Path, turn_idx: int) -> Path:
    import pickle
    save_path = run_dir / f"world_turn_{turn_idx:03d}.pkl"
    with open(save_path, "wb") as f:
        pickle.dump(world, f)
    return save_path


def _write_error_turn(
    run_dir: Path,
    draft: TurnDraft,
    turn_idx: int,
    stage: str,
    exc: Exception,
) -> Path:
    """Persist failed turn evidence so live play errors are debuggable."""
    raw_writer_output = getattr(exc, "raw_text", "")
    draft.hard_audit = {
        "passed": False,
        "issues": [
            {
                "severity": "hard_fail",
                "type": f"{stage}_failure",
                "reason": str(exc),
                "repair_instruction": "Inspect error_traceback and raw outputs before retrying.",
            }
        ],
        "medium_issues": [],
        "alignment_check": {},
        "error_stage": stage,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "error_traceback": traceback.format_exc(),
    }
    if raw_writer_output:
        draft.hard_audit["raw_writer_output"] = raw_writer_output

    sc = TurnScorecard(turn_id=draft.draft_id)
    sc.hard_failures.append(f"{stage}_failure")
    sc.hard_issue_count = 1
    sc.grounding_score = 0.0
    sc.patch_alignment_score = 0.0
    sc.action_understanding_score = 0.0
    sc.missing_player_output = not bool(draft.player_output.strip())
    sc.player_experience_score = sc.compute_player_experience()
    sc.notes.append(f"{stage}_failure: {type(exc).__name__}: {exc}")
    if raw_writer_output:
        sc.notes.append("raw_writer_output_saved")
    draft.scorecard = sc.to_json()

    path = run_dir / f"turn_{turn_idx:03d}_error.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(draft.to_json(), f, ensure_ascii=False, indent=2)
    return path


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    run_id = f"play_{uuid.uuid4().hex[:8]}"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    world = build()
    history: list[str] = []
    turn_idx = 0
    scorecards: list[dict] = []

    logger = RunLogger(run_id, run_dir)

    _clear()
    print("=" * 60)
    print("  MetaRPG Agentic v0.6.1 — 交互模式")
    print("=" * 60)
    print("\n  提示: /look 查看场景  /inv 查看背包  /save 存档  /quit 退出")
    print("\n  你推开了灰港酒馆的门...")

    packet = build_story_packet(world)
    _print_scene(packet)

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not raw:
            continue

        if raw in {"/quit", "/q", "退出"}:
            print("\n存档并退出...")
            _save_world(world, run_dir, turn_idx)
            hard_failures = []
            medium_issues = []
            soft_issues = []
            for sc in scorecards:
                hard_failures.extend(sc.get("hard_failures", []))
                medium_issues.extend(sc.get("medium_issues", []))
                soft_issues.extend(sc.get("soft_issues", []))
            logger.close(
                turns_attempted=turn_idx,
                turns_completed=turn_idx,
                scorecards=scorecards,
                hard_failures=hard_failures,
                medium_issues=medium_issues,
                soft_issues=soft_issues,
            )
            print(f"存档: {run_dir}")
            break

        if raw in {"/look", "/l", "看"}:
            packet = build_story_packet(world)
            _print_scene(packet)
            continue

        if raw in {"/inv", "/i", "背包"}:
            packet = build_story_packet(world)
            inv = packet.get("player_context", {}).get("inventory_or_handheld", [])
            print(f"\n  携带: {', '.join(inv) if inv else '（空）'}")
            continue

        if raw in {"/save", "存档"}:
            path = _save_world(world, run_dir, turn_idx)
            print(f"\n  已存档: {path.name}")
            continue

        # Normal turn
        turn_idx += 1
        player_input = raw
        print(f"\n  [回合 {turn_idx}] 你: {player_input}")
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

        # 2. Writer
        t0 = time.time()
        try:
            writer_output = run_writer(story_packet, player_input)
            draft.writer_output = writer_output
            draft.candidate_patch = writer_output.candidate_patch
            logger.emit(turn_idx, "writer", "writer_success", f"segments={len(writer_output.segments)}")
        except Exception as e:
            print(f"\n  [Writer 错误] {e}")
            logger.log_error(turn_idx, "writer", type(e).__name__, str(e), traceback.format_exc())
            err_path = _write_error_turn(run_dir, draft, turn_idx, "writer", e)
            print(f"  [错误已记录] {err_path}")
            history.append(player_input)
            continue

        # 3. Translator
        try:
            claims = run_translator(writer_output.segments, story_packet)
            draft.translated_claims = claims
            logger.emit(turn_idx, "translator", "translator_success", f"claims={len(claims)}")
        except Exception as e:
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

        # 6. Soft Auditor (skip if hard failures)
        if audit["passed"]:
            try:
                soft_issues = run_soft_auditor(
                    writer_output.segments,
                    history,
                    [e.__dict__ for e in writer_output.candidate_patch],
                )
                draft.soft_audit = {"passed": len(soft_issues) == 0, "issues": [i.__dict__ for i in soft_issues]}
                logger.emit(turn_idx, "soft_audit", "soft_audit_success", f"issues={len(soft_issues)}")
            except Exception as e:
                logger.log_error(turn_idx, "soft_auditor", type(e).__name__, str(e))
                draft.soft_audit = {"passed": True, "issues": []}
        else:
            draft.soft_audit = {"passed": False, "issues": []}

        # 7. Commit
        if audit["passed"]:
            admitted = writer_output.candidate_patch
        else:
            admitted = [
                e for e in writer_output.candidate_patch
                if e.kind in {"transient_event", "observe_reaction", "journal_note"}
            ]
        draft.admitted_patch = admitted
        draft.final_segments = writer_output.segments
        draft.player_output = "\n".join(s.text for s in writer_output.segments)

        if admitted:
            result = commit_turn(world, admitted, writer_output.segments)
            logger.emit(turn_idx, "commit", "commit_success", f"turn={world.turn}")
        else:
            result = {"delta": {}, "player_output": draft.player_output, "turn": world.turn}
            logger.emit(turn_idx, "commit", "commit_success", "nothing_admitted")

        # 8. Score
        sc = TurnScorecard(turn_id=draft.draft_id)
        sc.hidden_leak_count = sum(1 for c in claims if c.kind == "hidden_fact_reference")
        sc.absent_entity_action_count = sum(1 for c in claims if c.kind == "remote_event")
        sc.raw_debug_exposure_count = len(scanner_findings.get("raw_event_id_hits", []))
        sc.patch_alignment_score = 1.0 if audit["alignment_check"].get("claims_without_patch_support", 0) == 0 else 0.5
        sc.action_understanding_score = 1.0 if writer_output.interpretation else 0.0
        sc.grounding_score = 1.0 if audit["passed"] else 0.0
        sc.repair_rounds = len(draft.rewrite_history)
        sc.rewrite_locality_score = 1.0 if sc.repair_rounds == 0 else 0.5
        for issue in audit.get("issues", []):
            sc.hard_failures.append(issue.get("type", ""))
        for issue in audit.get("medium_issues", []):
            sc.medium_issues.append(issue.get("type", ""))
        sc.hard_issue_count = len(audit.get("issues", []))
        sc.medium_issue_count = len(audit.get("medium_issues", []))
        soft_audit = draft.soft_audit or {}
        for issue in soft_audit.get("issues", []):
            sc.soft_issues.append(issue.get("type", ""))
        sc.soft_issue_count = len(soft_audit.get("issues", []))
        if not draft.player_output.strip():
            sc.missing_player_output = True
            sc.notes.append("missing_player_output")
        sc.player_experience_score = sc.compute_player_experience()
        draft.scorecard = sc.to_json()
        scorecards.append(sc.to_json())

        # Output
        _print_output(writer_output.segments)
        _print_audit(audit)
        _print_score(sc)

        # Save turn log
        turn_path = run_dir / f"turn_{turn_idx:03d}.json"
        with open(turn_path, "w", encoding="utf-8") as f:
            json.dump(draft.to_json(), f, ensure_ascii=False, indent=2)
        logger.emit(turn_idx, "turn", "turn_written", str(turn_path.name))

        history.append(player_input)

    print(f"\n日志保存至: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
