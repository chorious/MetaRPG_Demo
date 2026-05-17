"""Canonical interactive CLI for agentic play.

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

import os
import sys
import uuid
from pathlib import Path

from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import run_agentic_turn
from metarpg.agentic.story_packet import build_story_packet
from metarpg.scenarios.greyfen import build


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


def _print_score(scorecard) -> None:
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
        print("  MetaRPG Agentic v0.6.3 — 交互模式")
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

            result = run_agentic_turn(
                world=world,
                player_input=player_input,
                turn_index=turn_idx,
                run_id=run_id,
                history=history,
                run_logger=logger,
            )

            _print_output(result["player_output"])
            _print_audit(result["draft"].hard_audit)
            _print_score(result["scorecard"])

            scorecards.append(result["scorecard"].to_json())
            history.append(player_input)

    finally:
        _close_run()

    print(f"\n日志保存至: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
