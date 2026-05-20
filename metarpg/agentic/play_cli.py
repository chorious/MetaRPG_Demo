"""Canonical interactive CLI for agentic play (v0.7.0 pipeline).

Usage:
    python -m metarpg.agentic.play_cli
    metarpg-agentic   (if installed via pyproject script)

Commands inside session:
    <anything>       Player action or speech
    /look            Show scene summary
    /inv             Show inventory
    /save            Save world state
    /quit            Exit and write summary
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from metarpg.agentic.narrative_grammar import load_grammar
from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import run_agentic_turn_v070
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.world_graph import world_from_seed


def _clear() -> None:
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


def _print_output(player_output: str) -> None:
    if not player_output.strip():
        print("\n  （没有输出）")
        return
    print("\n" + "-" * 50)
    print(player_output)
    print("-" * 50)


def _print_v070_audit(result: dict[str, Any]) -> None:
    val = result.get("validation")
    post = result.get("post_render")
    tx = result.get("transaction")

    if val and val.issues:
        print("\n  [验证]")
        for issue in val.issues:
            severity = "!" if issue.severity == "hard_fail" else "~"
            print(f"    {severity} [{issue.severity}] {issue.type}: {issue.reason}")

    if post:
        status = post.get("status", "pass")
        issues = post.get("issues", [])
        if status == "failed":
            print("\n  [渲染检查未通过]")
        elif status == "repaired":
            print("\n  [渲染已修复]")
        for issue in issues:
            if isinstance(issue, dict):
                print(f"    ! {issue.get('type', issue)}")
            else:
                print(f"    ! {issue}")

    if tx:
        assumptions = tx.assumptions
        if any(a.get("source") == "fallback" for a in assumptions):
            print("\n  [注意] 本回合使用 fallback 输出")
        if any(a.get("source") == "unreachable_location_response" for a in assumptions):
            print("\n  [注意] 目标地点不可达")
        if any(a.get("source") == "absence_response" for a in assumptions):
            print("\n  [注意] 目标不在场")


def _print_score(scorecard: TurnScorecard) -> None:
    print(f"\n  [评分] 体验={scorecard.player_experience_score:.2f}  grounding={scorecard.grounding_score:.2f}", end="")
    if scorecard.hard_issue_count:
        print(f"  硬问题={scorecard.hard_issue_count}", end="")
    if scorecard.medium_issue_count:
        print(f"  中等问题={scorecard.medium_issue_count}", end="")
    if scorecard.soft_issue_count:
        print(f"  软性={scorecard.soft_issue_count}", end="")
    print()


def _save_world(world, run_dir: Path, turn_idx: int) -> Path:
    import pickle
    save_path = run_dir / f"world_turn_{turn_idx:03d}.pkl"
    with open(save_path, "wb") as f:
        pickle.dump(world, f)
    return save_path


def _build_scorecard_v070(result: dict[str, Any]) -> TurnScorecard:
    """Build a truthful scorecard from v0.7.0 turn result."""
    tx = result.get("transaction")
    val = result.get("validation")
    post = result.get("post_render")

    sc = TurnScorecard(turn_id=result.get("draft_id", ""))

    # Grounding: validator + post-render
    sc.grounding_score = 1.0
    if val:
        if val.status == "accepted":
            sc.grounding_score = 1.0
        elif val.status == "downgraded":
            sc.grounding_score = 0.5
        else:
            sc.grounding_score = 0.0

    post_status = post.get("status", "pass") if post else "pass"
    if post_status == "failed":
        sc.grounding_score = 0.0
    elif post_status == "repaired":
        sc.grounding_score = min(sc.grounding_score, 0.5)

    # Validator issues
    if val:
        for issue in val.issues:
            if issue.severity == "hard_fail":
                sc.hard_failures.append(issue.type)
            else:
                sc.medium_issues.append(issue.type)

    sc.hard_issue_count = len(sc.hard_failures)
    sc.medium_issue_count = len(sc.medium_issues)

    # Post-render issues
    if post:
        for issue in post.get("issues", []):
            if isinstance(issue, dict):
                sc.soft_issues.append(issue.get("type", str(issue)))
            else:
                sc.soft_issues.append(str(issue))

    sc.soft_issue_count = len(sc.soft_issues)

    # Missing output
    prose = result.get("player_output", "")
    if not prose or not prose.strip():
        sc.missing_player_output = True

    # v0.7.4.1 experience gates
    assumptions = tx.assumptions if tx else []
    is_fallback = any(a.get("source") == "fallback" for a in assumptions)
    is_unreachable = any(a.get("source") == "unreachable_location_response" for a in assumptions)
    is_absence = any(a.get("source") == "absence_response" for a in assumptions)

    notes: list[str] = []
    if is_fallback:
        notes.append("fallback")
    if is_unreachable:
        notes.append("unreachable")
    if is_absence:
        notes.append("absence")
    if post_status == "repaired":
        notes.append("post_render_repaired")
    elif post_status == "failed":
        notes.append("post_render_failed")
    sc.notes = notes

    # Base experience score
    sc.player_experience_score = sc.compute_player_experience()

    # v0.7.4.1: fallback/unreachable/absence turns cannot get full score
    if is_fallback or is_unreachable or is_absence:
        sc.player_experience_score = min(sc.player_experience_score, 0.5)

    return sc


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    run_id = f"play_{uuid.uuid4().hex[:8]}"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    seed_path = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")
    grammar_path = Path("metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml")
    seed = load_seed(seed_path)
    grammar = load_grammar(grammar_path)
    world = world_from_seed(seed)

    history: list[str] = []
    turn_idx = 0
    scorecards: list[dict] = []

    logger = RunLogger(run_id, run_dir)
    _run_closed = False

    def _close_run() -> None:
        nonlocal _run_closed
        if _run_closed:
            return
        _run_closed = True
        hard_failures: list[str] = []
        medium_issues: list[str] = []
        soft_issues: list[str] = []
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

    try:
        _clear()
        print("=" * 60)
        print("  MetaRPG Agentic v0.7.0 — 交互模式")
        print("=" * 60)
        print("\n  提示: /look 查看场景  /inv 查看背包  /save 存档  /quit 退出")
        print("\n  你站在灰烬之窖的入口，门槛上覆着一层薄薄的黑灰...")

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
                _close_run()
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

            result = run_agentic_turn_v070(
                world=world,
                player_input=player_input,
                turn_index=turn_idx,
                run_id=run_id,
                seed=seed,
                grammar=grammar,
                history=history,
                run_logger=logger,
            )

            _print_output(result["player_output"])
            _print_v070_audit(result)

            scorecard = _build_scorecard_v070(result)
            _print_score(scorecard)

            # Persist turn and scorecard for analyze_play_run.py
            _persist_v070_turn(result, scorecard, logger, turn_idx)
            scorecards.append(scorecard.to_json())
            history.append(player_input)

    finally:
        _close_run()

    print(f"\n日志保存至: {run_dir}")
    return 0


def _persist_v070_turn(
    result: dict[str, Any],
    scorecard: TurnScorecard,
    logger: RunLogger,
    turn_idx: int,
) -> None:
    """Write a lightweight turn summary for downstream analysis."""
    tx = result.get("transaction")
    val = result.get("validation")
    post = result.get("post_render")

    turn_data = {
        "draft_id": result.get("draft_id", ""),
        "player_input": result.get("player_input", ""),
        "player_output": result.get("player_output", ""),
        "committed": result.get("committed", False),
        "turn_wall_time_s": result.get("turn_wall_time_s", 0.0),
        "l2_checks_run": result.get("l2_checks_run", 0),
        "validation_status": val.status if val else "",
        "validator_issues": [
            {"severity": i.severity, "type": i.type, "reason": i.reason}
            for i in (val.issues if val else [])
        ],
        "post_render_status": post.get("status", "") if post else "",
        "post_render_issues": post.get("issues", []) if post else [],
        "assumptions": tx.assumptions if tx else [],
        "operations": [
            {"kind": op.kind, "params": op.params}
            for op in (tx.operations if tx else [])
        ],
    }
    path = logger.run_dir / f"turn_{turn_idx:03d}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(turn_data, f, ensure_ascii=False, indent=2)

    logger.write_scorecard(scorecard.to_json(), turn_idx)


if __name__ == "__main__":
    sys.exit(main())
