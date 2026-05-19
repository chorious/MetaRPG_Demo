"""Agentic v0.7.0 — Dungeon smoke test (Ashen Vault).

Routes through run_agentic_turn_v070 for the transaction-first pipeline.
Requires live LLM endpoints: local vLLM (Director) + DeepSeek Flash (Renderer).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, r"E:\GameDesign\MetaRPG_Dev")

from metarpg.agentic.narrative_grammar import load_grammar
from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import run_agentic_turn_v070
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.world_graph import world_from_seed


def _print_turn_result(turn_idx: int, result: dict, player_input: str) -> None:
    """Print verbose turn diagnostics for v0.7.0 pipeline."""
    print(f"\n{'='*70}")
    print(f"TURN {turn_idx}: {player_input}")
    print("=" * 70)

    frame = result.get("narrative_frame")
    if frame:
        print(f"\n[1] NarrativeFrame")
        print(f"    Beat: {frame.beat}")
        print(f"    Active hooks: {frame.active_hooks}")
        print(f"    Candidate hints: {frame.candidate_hints}")
        print(f"    Motifs: {frame.motifs_to_use}")
        print(f"    Allowed levels: {frame.allowed_commitment_levels}")
        print(f"    Forbidden: {frame.forbidden_moves}")

    tx = result.get("transaction")
    if tx:
        print(f"\n[2] TurnTransaction")
        print(f"    Operations ({len(tx.operations)}):")
        for op in tx.operations:
            print(f"      {op.kind}: {json.dumps(op.params, ensure_ascii=False)}")
        print(f"    Commitments ({len(tx.commitments)}):")
        for c in tx.commitments:
            print(f"      [{c.level}] {c.description}")
        if tx.assumptions:
            print(f"    Assumptions: {tx.assumptions}")

    val = result.get("validation")
    if val:
        print(f"\n[3] Validation: {val.status}")
        if val.issues:
            print(f"    Issues ({len(val.issues)}):")
            for iss in val.issues:
                print(f"      [{iss.severity}] {iss.type}: {iss.reason}")
        if val.downgrades:
            print(f"    Downgrades ({len(val.downgrades)}):")
            for d in val.downgrades:
                print(f"      {d.original_commitment} -> {d.new_commitment}: {d.reason}")

    commit = result.get("commit")
    if commit:
        print(f"\n[4] Commit: turn={commit.get('turn')}")
        for k, v in commit.get("delta", {}).items():
            if v:
                print(f"    {k}: {v}")

    print(f"\n[5] Player output")
    print(f"    {result.get('player_output', '').replace(chr(10), chr(10)+'    ')}")

    check = result.get("post_render")
    if check:
        print(f"\n[6] Post-render check: {check['status']}")
        if check["issues"]:
            for issue in check["issues"]:
                print(f"    ! {issue}")
        else:
            print("    Clean")

    print(f"\n[7] Wall time: {result.get('turn_wall_time_s', 0):.2f}s")
    print(f"    Committed: {result.get('committed')}")
    print(f"    Error: {result.get('error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.7.0 Ashen Vault smoke test")
    parser.add_argument("--turns", type=int, default=3, help="Number of turns to run (default 3)")
    parser.add_argument("--extended", action="store_true", help="Run 20-turn extended sequence")
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    turn_count = 20 if args.extended else args.turns

    run_id = f"v070_smoke_{uuid.uuid4().hex[:8]}"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(run_id, run_dir)

    seed_path = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")
    grammar_path = Path("metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml")
    seed = load_seed(seed_path)
    grammar = load_grammar(grammar_path)
    world = world_from_seed(seed)

    # Scripted player inputs for deterministic evaluation
    mvp_inputs = [
        "我检查门槛上的黑灰。",
        "我问艾伦这灰是怎么回事。",
        "我去看那扇封闭的下层门。",
    ]

    extended_inputs = [
        "我检查门槛上的黑灰。",
        "我问艾伦这灰是怎么回事。",
        "我去看那扇封闭的下层门。",
        "我试着推开那扇门。",
        "我搜索旧卫兵室。",
        "我回到入口厅。",
        "我给艾伦一些水。",
        "我检查积水阶梯。",
        "我触摸门上的标记。",
        "我等待一会儿。",
        "我问艾伦关于下层密室的事。",
        "我沿着积水阶梯往下走。",
        "我检查墙壁上的痕迹。",
        "我拿出火把照亮四周。",
        "我倾听下面的声音。",
        "我回到封闭下层门。",
        "我尝试找到开门的方法。",
        "我检查地上的灰烬形状。",
        "我问艾伦是否愿意一起下去。",
        "我再次检查那扇门的封印。",
    ]

    inputs = extended_inputs[:turn_count]
    if turn_count <= 3:
        inputs = mvp_inputs[:turn_count]

    print("=" * 70)
    print(f"Agentic Dungeon Smoke Test (v0.7.0 transaction-first)  RunID: {run_id}")
    print(f"Turns: {turn_count}  Seed: {seed.title}")
    print("=" * 70)

    results: list[dict] = []
    history: list[str] = []

    for turn_idx, player_input in enumerate(inputs, start=1):
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
        _print_turn_result(turn_idx, result, player_input)
        results.append(result)
        history.append(player_input)

    # Summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print("=" * 70)

    pass_count = sum(1 for r in results if r["post_render"]["status"] == "pass")
    repair_count = sum(1 for r in results if r["post_render"]["status"] == "light_repair")
    error_count = sum(1 for r in results if r["error"] is not None)
    fallback_count = sum(
        1 for r in results
        if any(a.get("source") == "fallback" for a in r["transaction"].assumptions)
    )
    absence_response_count = sum(
        1 for r in results
        if any(a.get("source") == "absence_response" for a in r["transaction"].assumptions)
    )
    l2_checks_run = sum(r.get("l2_checks_run", 0) for r in results)

    total_time = sum(r.get("turn_wall_time_s", 0) for r in results)

    print(f"Turns run:     {len(results)}")
    print(f"Post-render pass:   {pass_count}")
    print(f"Post-render repair: {repair_count}")
    print(f"Errors:        {error_count}")
    print(f"Fallbacks:     {fallback_count}")
    print(f"Absence responses:  {absence_response_count}")
    print(f"L2 checks run:      {l2_checks_run}")
    print(f"Total wall time: {total_time:.2f}s  (avg {total_time/len(results):.2f}s)")

    # Acceptance criteria for 20-turn
    if turn_count >= 20:
        hints_surfaceed = len({h for r in results for h in r["narrative_frame"].candidate_hints})
        hooks_engaged = len({h for r in results for h in r["narrative_frame"].active_hooks})
        motifs_used = len({m for r in results for m in r["narrative_frame"].motifs_to_use})
        leaks = sum(1 for r in results if any("Hidden truth" in i for i in r["post_render"]["issues"]))

        print(f"\n20-turn targets:")
        print(f"  Hints surfaced: {hints_surfaceed} (target >=5)")
        print(f"  Hooks engaged:  {hooks_engaged} (target >=3)")
        print(f"  Motifs used:    {motifs_used} (target >=2)")
        print(f"  Hidden leaks:   {leaks} (target 0)")

    print(f"\nLogs saved to: {run_dir}")
    print("=" * 70)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
