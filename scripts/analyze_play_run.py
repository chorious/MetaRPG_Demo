"""Analyzer for play-run artifacts (v0.7.5).

Reads turn_NNN.json + scorecard_NNN.json + run_manifest.json and computes
experience-gate metrics with stable diagnostics.

Supports both legacy v0.6.6 writer-first monolithic turns and v0.7.x
transaction-first split artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_semantic_judgments(turn: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract semantic judgments from v0.7 or legacy format."""
    post = turn.get("post_render", {})
    if isinstance(post, dict) and post.get("semantic_judgments"):
        return post["semantic_judgments"]
    return []


def _extract_post_render_status(turn: dict[str, Any]) -> str:
    """v0.7 has post_render_status or nested post_render dict; legacy uses soft_audit."""
    if "post_render_status" in turn:
        return turn["post_render_status"]
    post = turn.get("post_render", {})
    if isinstance(post, dict) and post.get("status"):
        return post["status"]
    soft = turn.get("soft_audit", {})
    if isinstance(soft, dict):
        if soft.get("passed") is False:
            return "failed"
        if soft.get("issues"):
            return "repaired"
    return "pass"


def _extract_post_render_issues(turn: dict[str, Any]) -> list[Any]:
    """v0.7 has post_render_issues or nested post_render dict; legacy uses soft_audit."""
    if "post_render_issues" in turn:
        return turn["post_render_issues"]
    post = turn.get("post_render", {})
    if isinstance(post, dict) and post.get("issues"):
        return post["issues"]
    soft = turn.get("soft_audit", {})
    if isinstance(soft, dict):
        return soft.get("issues", [])
    return []


def _extract_validator_issues(turn: dict[str, Any]) -> list[dict[str, Any]]:
    """v0.7 has validator_issues; legacy uses hard_audit.issues."""
    if "validator_issues" in turn:
        return turn["validator_issues"]
    hard = turn.get("hard_audit", {})
    if isinstance(hard, dict):
        return hard.get("issues", [])
    return []


def _extract_scorecard(turn: dict[str, Any]) -> dict[str, Any]:
    """Scorecard may be nested in turn (legacy) or separate file."""
    return turn.get("scorecard", {})


def _extract_hidden_truths(turn: dict[str, Any]) -> list[str]:
    """Extract hidden truths and their aliases."""
    # v0.7.5.1: read from world.hidden_truths if present
    world = turn.get("world", {})
    if world and "hidden_truths" in world:
        hidden = world["hidden_truths"]
        results = []
        for h in hidden:
            if isinstance(h, dict):
                pred = h.get("predicate", "")
                args = h.get("args", [])
                alias = h.get("alias", "")
                if pred:
                    results.append(f"{pred}({', '.join(str(a) for a in args)})")
                if alias:
                    results.append(alias)
        return results
    # legacy fallback
    hidden = (
        turn.get("story_packet", {})
        .get("auditor_only", {})
        .get("hidden_truths", [])
    )
    results = []
    for h in hidden:
        if isinstance(h, dict):
            pred = h.get("predicate", "")
            args = h.get("args", [])
            alias = h.get("alias", "")
            if pred:
                results.append(f"{pred}({', '.join(str(a) for a in args)})")
            if alias:
                results.append(alias)
    return results


def _extract_public_facts(turn: dict[str, Any]) -> list[str]:
    """Extract public facts from world.facts, admitted_patch, and known_facts."""
    facts = []
    # v0.7.5.1: world.facts is the primary source
    world = turn.get("world", {})
    if world and "facts" in world:
        facts.extend(world["facts"])
    # From admitted patch (legacy)
    for patch in turn.get("admitted_patch", []):
        if isinstance(patch, dict):
            kind = patch.get("kind", "")
            args = patch.get("args", {})
            if kind == "add_fact":
                pred = args.get("predicate", "")
                aargs = args.get("args", [])
                if pred:
                    facts.append(f"{pred}({', '.join(str(a) for a in aargs)})")
            elif kind in ("transient_event", "journal_note", "relation_delta"):
                desc = args.get("description") or args.get("content") or json.dumps(args, ensure_ascii=False)
                facts.append(desc)
    # From known facts (legacy)
    known = (
        turn.get("story_packet", {})
        .get("player_context", {})
        .get("known_facts", [])
    )
    facts.extend(known)
    # From player_output as public text
    prose = turn.get("player_output", "")
    if prose:
        facts.append(prose)
    return facts


def _check_state_continuity(prev_turn: dict[str, Any], curr_turn: dict[str, Any]) -> list[dict[str, Any]]:
    """Heuristic cross-turn state continuity check."""
    issues = []
    prev_output = prev_turn.get("player_output", "")
    curr_output = curr_turn.get("player_output", "")
    prev_facts = set(_extract_public_facts(prev_turn))
    curr_facts = set(_extract_public_facts(curr_turn))

    # drank -> untouched
    drink_acquired = any(
        "酒" in f or "drink" in f.lower() or "ale" in f.lower() or "麦酒" in f
        for f in prev_facts
    )
    if drink_acquired and curr_output and "还没碰" in curr_output:
        issues.append({
            "code": "METARPG_STATE_CONTINUITY_BREAK",
            "severity": "error",
            "type": "drank_then_untouched",
            "evidence": "Previous turn had drink acquisition, current prose claims untouched",
            "repair_hint": "ensure state continuity across turns",
        })

    # moved -> still here contradiction (heuristic)
    prev_location = prev_turn.get("story_packet", {}).get("scene", {}).get("location", "")
    curr_location = curr_turn.get("story_packet", {}).get("scene", {}).get("location", "")
    if prev_location and curr_location and prev_location != curr_location:
        if curr_output and ("还在" + prev_location in curr_output or "still in" + prev_location.lower() in curr_output.lower()):
            issues.append({
                "code": "METARPG_STATE_CONTINUITY_BREAK",
                "severity": "error",
                "type": "moved_but_still_here",
                "evidence": f"Moved from {prev_location} to {curr_location} but prose claims still in {prev_location}",
                "repair_hint": "ensure location state is consistent",
            })

    # acquired -> absent
    for f in prev_facts:
        if f.startswith("has("):
            parts = f.split(",")
            if len(parts) >= 2:
                item = parts[-1].strip(" )")
                if curr_output and item and len(item) > 2:
                    if ("不见" in curr_output or "丢失" in curr_output or " absent" in curr_output.lower()):
                        # Check if item is mentioned as absent
                        if item.lower() in curr_output.lower():
                            issues.append({
                                "code": "METARPG_STATE_CONTINUITY_BREAK",
                                "severity": "error",
                                "type": "acquired_then_absent",
                                "evidence": f"Previous turn had {item}, current prose claims absent",
                                "repair_hint": "ensure inventory state is consistent",
                            })

    return issues


def analyze_run(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)

    turn_files = sorted(run_dir.glob("turn_*.json"))
    scorecard_files = sorted(run_dir.glob("scorecard_*.json"))

    turns: list[dict[str, Any]] = []
    for tf in turn_files:
        data = _load_json(tf)
        if data is not None:
            turns.append(data)

    scorecards: list[dict[str, Any]] = []
    for sf in scorecard_files:
        data = _load_json(sf)
        if data is not None:
            scorecards.append(data)

    manifest = _load_json(run_dir / "run_manifest.json")

    # v0.7.5 experience-gate counters
    fallback_full_score_count = 0
    perspective_shift_count = 0
    state_continuity_issue_count = 0
    hidden_public_fact_overlap_count = 0
    hidden_truth_semantic_reveal_count = 0
    soft_audit_unrepaired_count = 0
    scorecard_overoptimism_count = 0
    diagnostics: list[dict[str, Any]] = []

    # Scorecard analysis
    for sc in scorecards:
        notes = sc.get("notes", [])
        exp = sc.get("player_experience_score", 1.0)
        if any("fallback" in str(n) for n in notes) and exp >= 1.0:
            fallback_full_score_count += 1
            diagnostics.append({
                "code": "METARPG_FALLBACK_FULL_SCORE",
                "severity": "error",
                "turn": sc.get("turn_id", "unknown"),
                "evidence": f"scorecard notes: {notes}, experience_score: {exp}",
                "source_artifact": "scorecard",
                "repair_hint": "fallback turn should not receive full score; check intent fulfillment and perspective",
            })

    # Turn-level analysis
    for i, turn in enumerate(turns):
        post_status = _extract_post_render_status(turn)
        post_issues = _extract_post_render_issues(turn)
        prose = turn.get("player_output", "")
        turn_id = turn.get("draft_id", f"turn_{i:03d}")

        if post_status == "failed":
            soft_audit_unrepaired_count += 1
            diagnostics.append({
                "code": "METARPG_SOFT_AUDIT_UNREPAIRED",
                "severity": "error",
                "turn": turn_id,
                "evidence": "post_render or soft_audit failed with no successful repair",
                "source_artifact": "turn",
                "repair_hint": "soft audit issues must be repaired or counted as unrepaired",
            })

        # Extract semantic judgments (v0.7)
        semantic_judgments = _extract_semantic_judgments(turn)

        # Perspective shift
        if semantic_judgments:
            for j in semantic_judgments:
                if isinstance(j, dict) and j.get("check") == "intent_fulfillment":
                    if j.get("category") == "perspective_shift" and j.get("verdict") == "reject":
                        perspective_shift_count += 1
                        diagnostics.append({
                            "code": "METARPG_PERSPECTIVE_SHIFT",
                            "severity": "error",
                            "turn": turn_id,
                            "evidence": str(j.get("evidence", "")),
                            "source_artifact": "semantic_judgment",
                            "repair_hint": "narrative must maintain 2nd-person perspective",
                        })
        else:
            # Legacy heuristic
            if prose and isinstance(prose, str) and "我" in prose and "你" not in prose:
                perspective_shift_count += 1
                diagnostics.append({
                    "code": "METARPG_PERSPECTIVE_SHIFT",
                    "severity": "warning",
                    "turn": turn_id,
                    "evidence": f"prose contains 我 without 你: {prose[:80]}...",
                    "source_artifact": "player_output",
                    "repair_hint": "narrative must maintain 2nd-person perspective",
                })

        # Hidden truth semantic reveal (v0.7)
        for j in semantic_judgments:
            if isinstance(j, dict) and j.get("check") == "hidden_truth_exposure":
                if j.get("verdict") in ("reject", "downgrade"):
                    hidden_truth_semantic_reveal_count += 1
                    diagnostics.append({
                        "code": "METARPG_HIDDEN_TRUTH_SEMANTIC_REVEAL",
                        "severity": "error",
                        "turn": turn_id,
                        "evidence": str(j.get("evidence", "")),
                        "source_artifact": "semantic_judgment",
                        "repair_hint": "hidden truth must not be semantically revealed in prose",
                    })

        # Hidden public fact overlap (precise)
        hidden_truths = _extract_hidden_truths(turn)
        public_facts = _extract_public_facts(turn)
        if hidden_truths and public_facts:
            public_text = " ".join(public_facts).lower()
            for ht in hidden_truths:
                if ht.lower() in public_text:
                    hidden_public_fact_overlap_count += 1
                    diagnostics.append({
                        "code": "METARPG_HIDDEN_PUBLIC_FACT_OVERLAP",
                        "severity": "error",
                        "turn": turn_id,
                        "evidence": f"hidden truth '{ht}' appears in public facts or prose",
                        "source_artifact": "turn",
                        "repair_hint": "hidden truths must not enter public facts or player output",
                    })

        # State continuity (cross-turn)
        if i > 0:
            continuity_issues = _check_state_continuity(turns[i - 1], turn)
            state_continuity_issue_count += len(continuity_issues)
            for issue in continuity_issues:
                issue["turn"] = turn_id
                diagnostics.append(issue)

    # Scorecard overoptimism
    for turn, sc in zip(turns, scorecards):
        exp = sc.get("player_experience_score", 1.0)
        val_issues = _extract_validator_issues(turn)
        post_status = _extract_post_render_status(turn)

        hard_in_validator = any(
            i.get("severity") == "hard_fail" for i in val_issues
        )
        post_failed = post_status == "failed"

        if exp >= 0.9 and (hard_in_validator or post_failed):
            scorecard_overoptimism_count += 1
            diagnostics.append({
                "code": "METARPG_SCORECARD_OVEROPTIMISM",
                "severity": "warning",
                "turn": turn.get("draft_id", "unknown"),
                "evidence": f"experience={exp} but validator/post_render has hard issues",
                "source_artifact": "scorecard",
                "repair_hint": "scorecard should reflect validator and post-render failures",
            })

    return {
        "turns_analyzed": len(turns),
        "scorecards_found": len(scorecards),
        "fallback_full_score_count": fallback_full_score_count,
        "perspective_shift_count": perspective_shift_count,
        "state_continuity_issue_count": state_continuity_issue_count,
        "hidden_public_fact_overlap_count": hidden_public_fact_overlap_count,
        "hidden_truth_semantic_reveal_count": hidden_truth_semantic_reveal_count,
        "soft_audit_unrepaired_count": soft_audit_unrepaired_count,
        "scorecard_overoptimism_count": scorecard_overoptimism_count,
        "diagnostics": diagnostics,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze play run artifacts")
    parser.add_argument("run_dir", type=Path, help="Path to run directory")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    result = analyze_run(args.run_dir)

    print("=" * 50)
    print("Play Run Analysis -- v0.7.5")
    print("=" * 50)
    print(f"Turns analyzed:   {result['turns_analyzed']}")
    print(f"Scorecards found: {result['scorecards_found']}")
    print()
    print(f"fallback_full_score_count:       {result['fallback_full_score_count']} (target 0)")
    print(f"perspective_shift_count:         {result['perspective_shift_count']} (target 0)")
    print(f"state_continuity_issue_count:    {result['state_continuity_issue_count']} (target 0)")
    print(f"hidden_public_fact_overlap:      {result['hidden_public_fact_overlap_count']} (target 0)")
    print(f"hidden_truth_semantic_reveal:    {result['hidden_truth_semantic_reveal_count']} (target 0)")
    print(f"soft_audit_unrepaired_count:     {result['soft_audit_unrepaired_count']} (target 0)")
    print(f"scorecard_overoptimism_count:    {result['scorecard_overoptimism_count']} (target 0)")

    all_zero = all(
        result[k] == 0
        for k in (
            "fallback_full_score_count",
            "perspective_shift_count",
            "state_continuity_issue_count",
            "hidden_public_fact_overlap_count",
            "hidden_truth_semantic_reveal_count",
            "soft_audit_unrepaired_count",
            "scorecard_overoptimism_count",
        )
    )
    print()
    print("ACCEPTED" if all_zero else "REJECTED")

    if args.json:
        json_bytes = json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")
        sys.stdout.buffer.write(json_bytes)
        sys.stdout.buffer.write(b"\n")

    return 0 if all_zero else 1


if __name__ == "__main__":
    sys.exit(main())
