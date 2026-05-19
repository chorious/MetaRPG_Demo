"""Artifact Analyzer — compute metrics from a v0.7.x agentic run directory.

Usage:
    python scripts/analyze_agentic_run.py runtime/agentic_runs/<run_id>
    python scripts/analyze_agentic_run.py --json runtime/agentic_runs/<run_id>
    python scripts/analyze_agentic_run.py --json --fail-on-invariant runtime/agentic_runs/<run_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


SEED_PATH = Path(__file__).parent.parent / "metarpg" / "data" / "seeds" / "dnd_ashen_vault_seed.yaml"

CANONICAL_HOOK_IDS: set[str] = set()


def _load_seed() -> dict[str, Any]:
    global CANONICAL_HOOK_IDS
    if SEED_PATH.exists():
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            seed = yaml.safe_load(f)
        hooks = seed.get("active_hooks", [])
        CANONICAL_HOOK_IDS = {h["id"] for h in hooks if isinstance(h, dict) and "id" in h}
    return {}


def _artifact_files(run_dir: Path) -> dict[int, dict[str, Path]]:
    """Group artifact files by turn index."""
    turns: dict[int, dict[str, Path]] = {}
    for p in run_dir.iterdir():
        if not p.is_file() or not p.name.startswith("artifact_"):
            continue
        # artifact_NNN_type.json
        parts = p.stem.split("_", 2)  # ["artifact", "NNN", "type"]
        if len(parts) < 3:
            continue
        try:
            turn_idx = int(parts[1])
        except ValueError:
            continue
        kind = parts[2]
        turns.setdefault(turn_idx, {})[kind] = p
    return turns


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _analyze_turn(
    turn_idx: int,
    artifacts: dict[str, Path],
) -> dict[str, Any]:
    """Analyze a single turn's artifacts."""

    resolved = _load(artifacts.get("resolved_intent"))
    frame = _load(artifacts.get("narrative_frame"))
    tx_raw = _load(artifacts.get("transaction_raw"))
    tx_val = _load(artifacts.get("transaction_validated"))
    post = _load(artifacts.get("post_render"))
    semantic = _load(artifacts.get("semantic_judgments"))
    motif_sched = _load(artifacts.get("motif_schedule"))

    result: dict[str, Any] = {"turn": turn_idx}

    # --- resolved_intent ---
    result["action_type"] = resolved.get("action_type", "") if resolved else ""
    result["has_unresolved"] = bool(resolved.get("unresolved")) if resolved else False
    result["absent_target_count"] = sum(
        1 for t in (resolved.get("targets", []) if resolved else [])
        if isinstance(t, dict) and t.get("available") is False
    )

    # --- narrative_frame ---
    active_hooks: list[str] = frame.get("active_hooks", []) if frame else []
    result["active_hooks"] = active_hooks
    result["invalid_active_hooks"] = [h for h in active_hooks if h not in CANONICAL_HOOK_IDS]
    result["candidate_hints_count"] = len(frame.get("candidate_hints", [])) if frame else 0
    result["motifs_to_use"] = frame.get("motifs_to_use", []) if frame else []

    # --- transaction_raw ---
    raw_note = ""
    if tx_raw:
        # v0.7.2.1: absence_response stores note at top level, not in director_raw_output
        # v0.7.3: deterministic_movement also stores note at top level
        top_note = tx_raw.get("note", "")
        if top_note.startswith("absence_response"):
            raw_note = "absence_response"
        elif top_note.startswith("deterministic_movement"):
            raw_note = "deterministic_movement"
        else:
            raw = tx_raw.get("director_raw_output")
            if raw is None:
                raw_note = "fallback"
            elif isinstance(raw, dict) and raw.get("note", "").startswith("absence_response"):
                raw_note = "absence_response"
            elif isinstance(raw, dict):
                raw_note = "director"
    result["source"] = raw_note

    # move_player missing destination check (raw transaction)
    raw_ops = (tx_raw.get("parsed", {}) if tx_raw else {}).get("operations", [])
    move_no_dest = False
    for op in raw_ops:
        if isinstance(op, dict) and op.get("kind") == "move_player":
            params = op.get("params", {})
            if "destination" not in params:
                move_no_dest = True
                break
    result["move_player_missing_destination"] = move_no_dest

    # --- transaction_validated ---
    val_status = tx_val.get("status", "") if tx_val else ""
    result["validator_status"] = val_status
    result["downgrade_records"] = tx_val.get("downgrades", []) if tx_val else []
    result["downgraded"] = val_status == "downgraded"
    result["rejected"] = val_status == "rejected"
    result["accepted"] = val_status in ("accepted", "downgraded")

    # --- post_render ---
    post_status = post.get("status", "") if post else ""
    result["post_render_status"] = post_status
    result["post_render_issues"] = post.get("issues", []) if post else []
    result["repair_attempted"] = post.get("repair_attempted", False) if post else False
    result["repair_success"] = post.get("repair_success", False) if post else False

    # L2 judgments from post_render artifact
    semantic_judgments = post.get("semantic_judgments", []) if post else []
    result["l2_judgments_count"] = len(semantic_judgments)
    result["l2_rejects"] = [
        j for j in semantic_judgments
        if isinstance(j, dict) and j.get("verdict") in ("reject", "downgrade")
    ]
    result["l2_hard_rejects"] = [
        j for j in semantic_judgments
        if isinstance(j, dict) and j.get("verdict") == "reject"
    ]
    result["hidden_truth_nonpass"] = [
        j for j in semantic_judgments
        if isinstance(j, dict)
        and j.get("check") == "hidden_truth_exposure"
        and j.get("verdict") in ("reject", "downgrade")
    ]

    # --- motif_schedule ---
    result["motif_debug"] = (motif_sched.get("debug", {}) if motif_sched else {})

    return result


def _compute_summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(turns)
    if total == 0:
        return {}

    # Source counts
    fallback_count = sum(1 for t in turns if t["source"] == "fallback")
    absence_count = sum(1 for t in turns if t["source"] == "absence_response")
    deterministic_move_count = sum(1 for t in turns if t["source"] == "deterministic_movement")
    input_guard_count = sum(1 for t in turns if t["source"] == "input_guard")

    # Validator
    accepted_turns = sum(1 for t in turns if t["accepted"])
    downgraded_turns = sum(1 for t in turns if t["downgraded"])
    rejected_turns = sum(1 for t in turns if t["rejected"])
    downgrade_records = sum(len(t["downgrade_records"]) for t in turns)

    # Post-render
    post_pass = sum(1 for t in turns if t["post_render_status"] == "pass")
    post_repair = sum(1 for t in turns if t["post_render_status"] == "repaired")
    post_failed = sum(1 for t in turns if t["post_render_status"] == "failed")
    # v0.7.3: repair loop metrics
    initial_failed = sum(
        1 for t in turns
        if t["post_render_status"] == "failed" and not t.get("repair_attempted")
    )
    repaired_count = sum(1 for t in turns if t["post_render_status"] == "repaired")
    repair_attempts = sum(1 for t in turns if t.get("repair_attempted"))

    # L2
    l2_judgments = sum(t["l2_judgments_count"] for t in turns)
    l2_rejects = sum(len(t["l2_rejects"]) for t in turns)
    l2_hard_rejects = sum(len(t["l2_hard_rejects"]) for t in turns)
    hidden_nonpass = sum(len(t["hidden_truth_nonpass"]) for t in turns)

    # Hooks
    all_active_hooks: set[str] = set()
    invalid_hooks: set[str] = set()
    for t in turns:
        for h in t["active_hooks"]:
            all_active_hooks.add(h)
            if h not in CANONICAL_HOOK_IDS:
                invalid_hooks.add(h)

    canonical_hooks_engaged = all_active_hooks & CANONICAL_HOOK_IDS
    hook_bearing_turns = sum(1 for t in turns if any(h in CANONICAL_HOOK_IDS for h in t["active_hooks"]))

    # Motifs
    all_motifs: set[str] = set()
    longest_no_motif = 0
    current_streak = 0
    for t in turns:
        if t["motifs_to_use"]:
            all_motifs.update(t["motifs_to_use"])
            current_streak = 0
        else:
            current_streak += 1
            longest_no_motif = max(longest_no_motif, current_streak)

    # Move
    move_missing_dest = sum(1 for t in turns if t["move_player_missing_destination"])

    # Unresolved
    unresolved_turns = sum(1 for t in turns if t["has_unresolved"])

    return {
        "turns": total,
        "sources": {
            "fallback": fallback_count,
            "absence_response": absence_count,
            "deterministic_movement": deterministic_move_count,
            "input_guard": input_guard_count,
            "director": total - fallback_count - absence_count - input_guard_count - deterministic_move_count,
        },
        "validator": {
            "accepted_turns": accepted_turns,
            "downgraded_turns": downgraded_turns,
            "rejected_turns": rejected_turns,
            "downgrade_records": downgrade_records,
        },
        "post_render": {
            "pass": post_pass,
            "repaired": post_repair,
            "failed": post_failed,
            "repair_attempts": repair_attempts,
        },
        "l2_semantic": {
            "judgments_run": l2_judgments,
            "rejects": l2_rejects,
            "hard_rejects": l2_hard_rejects,
            "hidden_truth_nonpass": hidden_nonpass,
        },
        "hooks": {
            "unique_canonical_engaged": len(canonical_hooks_engaged),
            "unique_total_active": len(all_active_hooks),
            "invalid_hook_ids": sorted(invalid_hooks),
            "hook_bearing_turns": hook_bearing_turns,
        },
        "motifs": {
            "unique_used": len(all_motifs),
            "longest_no_motif_streak": longest_no_motif,
        },
        "operations": {
            "move_player_missing_destination": move_missing_dest,
        },
        "resolution": {
            "unresolved_turns": unresolved_turns,
            "absent_target_turns": sum(1 for t in turns if t["absent_target_count"] > 0),
        },
    }


def _invariant_violations(summary: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if summary["operations"]["move_player_missing_destination"] > 0:
        violations.append(
            f"move_player_missing_destination={summary['operations']['move_player_missing_destination']}"
        )
    if summary["hooks"]["invalid_hook_ids"]:
        violations.append(
            f"invalid_hook_ids={summary['hooks']['invalid_hook_ids']}"
        )
    if summary["l2_semantic"]["hard_rejects"] > 0:
        violations.append(
            f"unrepaired_l2_rejects={summary['l2_semantic']['hard_rejects']}"
        )
    if summary["l2_semantic"]["hidden_truth_nonpass"] > 0:
        violations.append(
            f"hidden_truth_nonpass={summary['l2_semantic']['hidden_truth_nonpass']}"
        )
    return violations


def _print_table(summary: dict[str, Any]) -> None:
    print("=" * 60)
    print("Agentic Run Analyzer -- v0.7.2.1")
    print("=" * 60)

    print(f"\nTurns: {summary['turns']}")

    print("\n--- Sources ---")
    for k, v in summary["sources"].items():
        print(f"  {k}: {v}")

    print("\n--- Validator ---")
    for k, v in summary["validator"].items():
        print(f"  {k}: {v}")

    print("\n--- Post-render ---")
    for k, v in summary["post_render"].items():
        print(f"  {k}: {v}")

    print("\n--- L2 Semantic ---")
    for k, v in summary["l2_semantic"].items():
        print(f"  {k}: {v}")

    print("\n--- Hooks ---")
    for k, v in summary["hooks"].items():
        print(f"  {k}: {v}")

    print("\n--- Motifs ---")
    for k, v in summary["motifs"].items():
        print(f"  {k}: {v}")

    print("\n--- Operations ---")
    for k, v in summary["operations"].items():
        print(f"  {k}: {v}")

    print("\n--- Resolution ---")
    for k, v in summary["resolution"].items():
        print(f"  {k}: {v}")

    violations = _invariant_violations(summary)
    if violations:
        print("\n!!! INVARIANT VIOLATIONS !!!")
        for v in violations:
            print(f"  - {v}")
    else:
        print("\n[OK] All invariants passed.")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze agentic run artifacts")
    parser.add_argument("run_dir", type=Path, help="Path to run directory")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--fail-on-invariant", action="store_true", help="Exit non-zero if invariant violated")
    args = parser.parse_args()

    _load_seed()

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        print(f"Error: not a directory: {run_dir}", file=sys.stderr)
        return 1

    artifact_map = _artifact_files(run_dir)
    if not artifact_map:
        print(f"Error: no artifacts found in {run_dir}", file=sys.stderr)
        return 1

    turns = []
    for turn_idx in sorted(artifact_map.keys()):
        turns.append(_analyze_turn(turn_idx, artifact_map[turn_idx]))

    summary = _compute_summary(turns)

    if args.json:
        output = {
            "run_dir": str(run_dir),
            "summary": summary,
            "turns": turns,
            "invariant_violations": _invariant_violations(summary),
        }
        json_bytes = json.dumps(output, indent=2, ensure_ascii=False).encode("utf-8")
        sys.stdout.buffer.write(json_bytes)
        sys.stdout.buffer.write(b"\n")
    else:
        _print_table(summary)

    if args.fail_on_invariant and _invariant_violations(summary):
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
