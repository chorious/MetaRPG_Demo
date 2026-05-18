"""Canonical agentic turn orchestration — v0.6.6 restored architecture.

Single entry point: run_agentic_turn()

Pipeline shape (v0.6.6 "Bold-first + Safe fallback"):
  1. Build story packet.
  2. Parallel: Bold Writer (Flash) + Feasibility (local Qwen).
  3. Audit Bold (translator + scanner + hard + soft).
  4. If Bold passes audit AND has segments -> commit, done (fast path).
  5. Else spawn Safe Writers (Qwen): safe_loose + safe_strict_<kind>.
  6. Audit each safe candidate.
  7. Decision tree: bold > safe_loose > safe_strict > refusal_fallback template.
  8. Commit winner. Empty-segment candidates are rejected outright (v0.6.6 P0).
  9. If Bold raises -> error path (v0.6.3 contract).

Compared to the simplified intermediate v0.6.6:
  - No Editor rewrite closed loop. Safety comes from parallel Safe Writers.
  - aggregate_v064_stats returns safe_loose / safe_strict / fallback metrics
    that the smoke test consumes.
"""
from __future__ import annotations

import time
import traceback
from statistics import median
from typing import Any

from metarpg.agentic import refusal_fallback
from metarpg.agentic.committer import commit_turn
from metarpg.agentic.feasibility import run_feasibility
from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.model_client import make_client
from metarpg.agentic.parallel_dispatch import Job, run_parallel
from metarpg.agentic.scanner import scan_segment
from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    FeasibilityReport,
    TurnDraft,
    WriterOutput,
)
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.agentic.soft_auditor_agent import run_soft_auditor
from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.translator_agent import run_translator
from metarpg.agentic.writer_agent import (
    WriterOutputError,
    run_writer,
    safe_mode_for_kind,
)


_PRIORITY_ORDER = ("bold", "safe_loose", "safe_strict")


def run_agentic_turn(
    *,
    world,
    player_input: str,
    turn_index: int,
    run_id: str,
    history: list[str] | None = None,
    run_logger=None,
) -> dict[str, Any]:
    """Run one complete agentic turn."""
    if history is None:
        history = []

    turn_start = time.perf_counter()
    draft = TurnDraft(
        draft_id=f"{run_id}_turn_{turn_index:03d}",
        player_input=player_input,
        pre_world_ref=f"greyfen_turn_{turn_index}",
    )

    if run_logger:
        run_logger.emit(turn_index, "turn", "turn_start", player_input)

    # 1. Story packet -------------------------------------------------------
    story_packet = build_story_packet(world)
    draft.story_packet = story_packet
    if run_logger:
        run_logger.emit(turn_index, "story_packet", "story_packet_built")

    flash_client = make_client("flash")
    local_client = make_client("local")

    # 2. Batch 1: Bold Writer (Flash) + Feasibility (Qwen) -----------------
    batch1_jobs = [
        Job(
            name="bold",
            fn=run_writer,
            args=(story_packet, player_input),
            kwargs={"client": flash_client, "mode": "bold", "temperature": 0.8},
        ),
        Job(
            name="feasibility",
            fn=run_feasibility,
            args=(story_packet, player_input),
            kwargs={"client": local_client},
        ),
    ]
    batch1 = run_parallel(batch1_jobs, max_workers=4)
    if run_logger:
        run_logger.emit(turn_index, "batch1", "batch1_complete")

    # 3. Resolve feasibility ------------------------------------------------
    feas_result = batch1.get("feasibility")
    if isinstance(feas_result, FeasibilityReport):
        feasibility = feas_result
    else:
        feasibility = FeasibilityReport(
            preserve_player_voice=_fallback_voice(player_input),
            world_response_kind="accept",
        )
        if isinstance(feas_result, Exception) and run_logger:
            run_logger.log_error(
                turn_index, "feasibility",
                type(feas_result).__name__, str(feas_result),
            )
    draft.feasibility = feasibility

    # 4. Bold exception -> error path --------------------------------------
    bold_result = batch1.get("bold")
    if not isinstance(bold_result, WriterOutput):
        exc = bold_result if isinstance(bold_result, Exception) else None
        return _emit_fatal_writer_failure(draft, exc, turn_index, run_logger)

    draft.writer_candidates["bold"] = bold_result

    # 5. Audit Bold ---------------------------------------------------------
    bold_audit = _audit_candidate(bold_result, story_packet, world, local_client)
    draft.candidate_audits["bold"] = bold_audit
    soft_bold = _run_soft_safe(bold_result, history)

    # 6. Fast path: Bold passes audit AND has segments ---------------------
    if bold_audit.get("passed") and bold_result.segments:
        winner_name = "bold"
        winner_output = bold_result
        winner_audit = bold_audit
        soft_audit = soft_bold
        if run_logger:
            run_logger.emit(
                turn_index, "decision", "winner_selected",
                "winner=bold (fast path)",
            )
    else:
        # 7. Batch 2: Safe Writers (Qwen) ----------------------------------
        strict_mode = safe_mode_for_kind(feasibility.world_response_kind)
        batch2_jobs = [
            Job(
                name="safe_loose",
                fn=run_writer,
                args=(story_packet, player_input),
                kwargs={
                    "client": local_client,
                    "mode": "safe_loose",
                    "feasibility": feasibility,
                    "temperature": 0.3,
                },
            ),
            Job(
                name="safe_strict",
                fn=run_writer,
                args=(story_packet, player_input),
                kwargs={
                    "client": local_client,
                    "mode": strict_mode,
                    "feasibility": feasibility,
                    "temperature": 0.5,
                },
            ),
        ]
        batch2 = run_parallel(batch2_jobs, max_workers=4)
        if run_logger:
            run_logger.emit(turn_index, "batch2", "batch2_complete")

        for name in ("safe_loose", "safe_strict"):
            result = batch2.get(name)
            if isinstance(result, WriterOutput):
                draft.writer_candidates[name] = result
                draft.candidate_audits[name] = _audit_candidate(
                    result, story_packet, world, local_client
                )
            elif isinstance(result, Exception) and run_logger:
                run_logger.log_error(
                    turn_index, name,
                    type(result).__name__, str(result),
                )

        winner_name, winner_output, winner_audit = _select_winner(
            draft.writer_candidates, draft.candidate_audits, feasibility,
        )
        if winner_name == "fallback":
            soft_audit = {"passed": True, "issues": []}
            draft.candidate_audits["fallback"] = winner_audit
        else:
            soft_audit = _run_soft_safe(winner_output, history)
        if run_logger:
            run_logger.emit(
                turn_index, "decision", "winner_selected",
                f"winner={winner_name}",
            )

    draft.winner_name = winner_name
    draft.writer_output = winner_output
    draft.soft_audit = soft_audit
    draft.translated_claims = winner_audit.get("translator_claims", [])
    draft.deterministic_scan = winner_audit.get("scanner", {})
    draft.candidate_patch = list(winner_output.candidate_patch)
    draft.hard_audit = {
        "passed": winner_audit.get("passed", True),
        "issues": winner_audit.get("issues", []),
        "medium_issues": winner_audit.get("medium_issues", []),
        "alignment_check": winner_audit.get("alignment_check", {}),
    }

    # 8. Commit -------------------------------------------------------------
    if draft.hard_audit["passed"]:
        admitted = list(winner_output.candidate_patch)
    else:
        admitted = [
            e for e in winner_output.candidate_patch
            if e.kind in {"transient_event", "observe_reaction", "journal_note"}
        ]
    draft.admitted_patch = admitted
    draft.final_segments = list(winner_output.segments)
    draft.player_output = "\n".join(s.text for s in winner_output.segments)

    if admitted:
        commit_turn(world, admitted, winner_output.segments)
        if run_logger:
            run_logger.emit(turn_index, "commit", "commit_success", f"turn={world.turn}")
    else:
        if run_logger:
            run_logger.emit(turn_index, "commit", "commit_success", "nothing_admitted")

    # 9. Scorecard ----------------------------------------------------------
    sc = _build_scorecard(
        draft, draft.translated_claims, draft.deterministic_scan,
        draft.hard_audit, winner_output,
    )
    sc.notes.append(f"winner={draft.winner_name}")
    draft.scorecard = sc.to_json()
    draft.turn_wall_time_s = time.perf_counter() - turn_start

    # 10. Persist -----------------------------------------------------------
    if run_logger:
        run_logger.write_turn(draft, turn_index)
        run_logger.write_scorecard(draft.scorecard, turn_index)

    return {
        "draft": draft,
        "scorecard": sc,
        "player_output": draft.player_output,
        "committed": bool(admitted),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fallback_voice(player_input: str) -> list[str]:
    cleaned = player_input.strip().replace('"', " ").replace("'", " ")
    tokens = [t for t in cleaned.split() if t]
    return tokens[:3] if tokens else []


def _select_winner(
    candidates: dict[str, WriterOutput],
    audits: dict[str, dict[str, Any]],
    feasibility: FeasibilityReport,
) -> tuple[str, WriterOutput, dict[str, Any]]:
    """Decision tree: bold > safe_loose > safe_strict > refusal_fallback.

    A candidate is eligible only if it (a) exists, (b) has at least one
    segment, and (c) passed hard audit.
    """
    for name in _PRIORITY_ORDER:
        cand = candidates.get(name)
        audit = audits.get(name, {})
        if cand is None or not cand.segments:
            continue
        if audit.get("passed"):
            return name, cand, audit

    fallback_output = refusal_fallback.generate(feasibility)
    fallback_audit = {
        "passed": True,
        "issues": [],
        "medium_issues": [],
        "alignment_check": {},
        "synthetic": True,
        "translator_claims": [],
        "scanner": {},
    }
    return "fallback", fallback_output, fallback_audit


def _emit_fatal_writer_failure(
    draft: TurnDraft,
    primary_exc: Exception | None,
    turn_index: int,
    run_logger,
) -> dict[str, Any]:
    """v0.6.3 contract: when Bold writer raises, write error turn and bail."""
    raw_text = getattr(primary_exc, "raw_text", "") if primary_exc else ""

    draft.writer_output = None
    draft.final_segments = []
    draft.player_output = ""
    draft.candidate_patch = []
    draft.hard_audit = {
        "passed": False,
        "issues": [{
            "severity": "hard_fail",
            "type": "writer_failure",
            "reason": str(primary_exc) if primary_exc else "bold writer failed",
        }],
        "medium_issues": [],
        "alignment_check": {},
    }
    draft.soft_audit = {"passed": False, "issues": []}
    draft.winner_name = ""

    sc = _build_scorecard(draft, [], {}, draft.hard_audit, None)
    draft.scorecard = sc.to_json()

    if run_logger:
        run_logger.write_error_turn(
            draft,
            turn_index,
            error_stage="writer",
            error_type=type(primary_exc).__name__ if primary_exc else "WriterFailed",
            error_message=str(primary_exc) if primary_exc else "bold writer produced no output",
            traceback_str=traceback.format_exc(),
            raw_output=raw_text,
        )
        run_logger.write_scorecard(draft.scorecard, turn_index)

    return {
        "draft": draft,
        "scorecard": sc,
        "player_output": "",
        "committed": False,
        "error": primary_exc,
    }


def _audit_candidate(
    candidate: WriterOutput,
    story_packet: dict[str, Any],
    world,
    local_client,
) -> dict[str, Any]:
    """Run Translator + Scanner + Hard Audit for one candidate."""
    try:
        claims = run_translator(candidate.segments, story_packet, client=local_client)
    except Exception as exc:
        claims = []
        translator_error = f"{type(exc).__name__}: {exc}"
    else:
        translator_error = ""

    scanner_findings: dict[str, Any] = {
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
    for s in candidate.segments:
        f = scan_segment(s.id, s.text, known_entities, known_locations, hidden_aliases)
        for k, v in f.items():
            if isinstance(v, list):
                scanner_findings.setdefault(k, []).extend(v)

    audit = run_hard_audit(
        story_packet,
        candidate.segments,
        claims,
        scanner_findings,
        candidate.candidate_patch,
        world,
    )
    audit["translator_claims"] = claims
    audit["scanner"] = scanner_findings
    if translator_error:
        audit["translator_error"] = translator_error
    return audit


def _run_soft_safe(candidate: WriterOutput, history: list[str]) -> dict[str, Any]:
    """Soft auditor with safe-default fallback."""
    try:
        issues = run_soft_auditor(
            candidate.segments,
            history,
            [e.__dict__ for e in candidate.candidate_patch],
        )
    except Exception:
        return {"passed": True, "issues": []}
    return {
        "passed": len(issues) == 0,
        "issues": [i.__dict__ for i in issues],
    }


def _build_scorecard(
    draft: TurnDraft,
    claims: list,
    scanner_findings: dict[str, Any],
    audit: dict[str, Any],
    writer_output,
) -> TurnScorecard:
    """Build a truthful scorecard from turn artifacts."""
    sc = TurnScorecard(turn_id=draft.draft_id)
    sc.hidden_leak_count = sum(1 for c in claims if getattr(c, "kind", "") == "hidden_fact_reference")
    sc.absent_entity_action_count = sum(1 for c in claims if getattr(c, "kind", "") == "remote_event")
    sc.raw_debug_exposure_count = len(scanner_findings.get("raw_event_id_hits", [])) if scanner_findings else 0
    sc.patch_alignment_score = 1.0 if audit.get("alignment_check", {}).get("claims_without_patch_support", 0) == 0 else 0.5
    sc.action_understanding_score = 1.0 if writer_output and getattr(writer_output, "interpretation", "") else 0.0
    sc.grounding_score = 1.0 if audit.get("passed") else 0.0
    sc.repair_rounds = 0  # Bold + Safe fallback: no in-turn rewrites
    sc.rewrite_locality_score = 1.0

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
    return sc


# ---------------------------------------------------------------------------
# Manifest aggregation (called by smoke_test / play_cli at close)
# ---------------------------------------------------------------------------


def aggregate_v064_stats(drafts: list[TurnDraft]) -> dict[str, Any]:
    """Build stats over a list of completed turn drafts."""
    if not drafts:
        return {}

    total = len(drafts)
    bold_pass = sum(
        1 for d in drafts
        if d.candidate_audits.get("bold", {}).get("passed")
    )
    safe_loose_pass = sum(
        1 for d in drafts
        if d.candidate_audits.get("safe_loose", {}).get("passed")
    )
    safe_strict_pass = sum(
        1 for d in drafts
        if d.candidate_audits.get("safe_strict", {}).get("passed")
    )
    fallback_count = sum(1 for d in drafts if d.winner_name == "fallback")
    wall_times = [d.turn_wall_time_s for d in drafts if d.turn_wall_time_s > 0]

    winner_distribution = {
        "bold": sum(1 for d in drafts if d.winner_name == "bold"),
        "safe_loose": sum(1 for d in drafts if d.winner_name == "safe_loose"),
        "safe_strict": sum(1 for d in drafts if d.winner_name == "safe_strict"),
        "fallback": fallback_count,
        "error": sum(1 for d in drafts if d.winner_name == ""),
    }

    return {
        "turns": total,
        "bold_pass_rate": bold_pass / total,
        "safe_loose_pass_rate": safe_loose_pass / total,
        "safe_strict_pass_rate": safe_strict_pass / total,
        "fallback_count": fallback_count,
        "median_turn_wall_time_s": median(wall_times) if wall_times else 0.0,
        "winner_distribution": winner_distribution,
    }
