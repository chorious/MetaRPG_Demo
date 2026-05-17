"""Canonical agentic turn orchestration.

Single entry point: run_agentic_turn()

This is the only canonical function that means:
"run one agentic turn from player_input to final player_output and artifacts"
"""
from __future__ import annotations

import traceback
from typing import Any

from metarpg.agentic.committer import commit_turn
from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.scanner import scan_segment
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.agentic.schemas import TurnDraft
from metarpg.agentic.soft_auditor_agent import run_soft_auditor
from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.translator_agent import run_translator
from metarpg.agentic.writer_agent import run_writer


def run_agentic_turn(
    *,
    world,
    player_input: str,
    turn_index: int,
    run_id: str,
    history: list[str] | None = None,
    run_logger=None,
) -> dict[str, Any]:
    """Run one complete agentic turn.

    Returns a dict with:
    - draft: TurnDraft (full lifecycle record)
    - scorecard: TurnScorecard
    - player_output: str
    - committed: bool
    - error: Exception | None
    """
    if history is None:
        history = []

    draft = TurnDraft(
        draft_id=f"{run_id}_turn_{turn_index:03d}",
        player_input=player_input,
        pre_world_ref=f"greyfen_turn_{turn_index}",
    )

    if run_logger:
        run_logger.emit(turn_index, "turn", "turn_start", player_input)

    # 1. Story packet
    story_packet = build_story_packet(world)
    draft.story_packet = story_packet
    if run_logger:
        run_logger.emit(turn_index, "story_packet", "story_packet_built")

    # 2. Writer
    raw_writer_output = ""
    try:
        writer_output = run_writer(story_packet, player_input)
        draft.writer_output = writer_output
        draft.candidate_patch = writer_output.candidate_patch
        raw_writer_output = str(getattr(writer_output, "raw_json", "") or "")
        if run_logger:
            run_logger.emit(turn_index, "writer", "writer_success", f"segments={len(writer_output.segments)}")
    except Exception as exc:
        raw_writer_output = getattr(exc, "raw_text", raw_writer_output)
        if run_logger:
            run_logger.log_error(turn_index, "writer", type(exc).__name__, str(exc), traceback.format_exc())
            run_logger.write_error_turn(
                draft,
                turn_index,
                error_stage="writer",
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback_str=traceback.format_exc(),
                raw_output=raw_writer_output,
            )
            run_logger.write_scorecard(draft.scorecard, turn_index)
        draft.writer_output = None
        draft.final_segments = []
        draft.player_output = ""
        draft.candidate_patch = []
        draft.hard_audit = {
            "passed": False,
            "issues": [{"severity": "hard_fail", "type": "writer_failure", "reason": str(exc)}],
            "medium_issues": [],
            "alignment_check": {},
        }
        draft.soft_audit = {"passed": False, "issues": []}
        sc = _build_scorecard(draft, [], {}, draft.hard_audit, None)
        draft.scorecard = sc.to_json()
        return {
            "draft": draft,
            "scorecard": sc,
            "player_output": "",
            "committed": False,
            "error": exc,
        }

    # 3. Translator
    try:
        claims = run_translator(writer_output.segments, story_packet)
        draft.translated_claims = claims
        if run_logger:
            run_logger.emit(turn_index, "translator", "translator_success", f"claims={len(claims)}")
    except Exception as exc:
        if run_logger:
            run_logger.log_error(turn_index, "translator", type(exc).__name__, str(exc))
        claims = []

    # 4. Scanner
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
    for s in writer_output.segments:
        findings = scan_segment(s.id, s.text, known_entities, known_locations, hidden_aliases)
        for k, v in findings.items():
            if isinstance(v, list):
                scanner_findings.setdefault(k, []).extend(v)
    draft.deterministic_scan = scanner_findings
    if run_logger:
        run_logger.emit(turn_index, "scanner", "scanner_success")

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
    if run_logger:
        run_logger.emit(turn_index, "hard_audit", "hard_audit_success", f"passed={audit['passed']}")

    # 6. Soft Auditor
    if audit["passed"]:
        try:
            soft_issues = run_soft_auditor(
                writer_output.segments,
                history,
                [e.__dict__ for e in writer_output.candidate_patch],
            )
            draft.soft_audit = {"passed": len(soft_issues) == 0, "issues": [i.__dict__ for i in soft_issues]}
            if run_logger:
                run_logger.emit(turn_index, "soft_audit", "soft_audit_success", f"issues={len(soft_issues)}")
        except Exception as exc:
            if run_logger:
                run_logger.log_error(turn_index, "soft_auditor", type(exc).__name__, str(exc))
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
        commit_turn(world, admitted, writer_output.segments)
        if run_logger:
            run_logger.emit(turn_index, "commit", "commit_success", f"turn={world.turn}")
    else:
        if run_logger:
            run_logger.emit(turn_index, "commit", "commit_success", "nothing_admitted")

    # 8. Score
    sc = _build_scorecard(draft, claims, scanner_findings, audit, writer_output)
    draft.scorecard = sc.to_json()

    # 9. Persist
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
    sc.raw_debug_exposure_count = len(scanner_findings.get("raw_event_id_hits", []))
    sc.patch_alignment_score = 1.0 if audit.get("alignment_check", {}).get("claims_without_patch_support", 0) == 0 else 0.5
    sc.action_understanding_score = 1.0 if writer_output and getattr(writer_output, "interpretation", "") else 0.0
    sc.grounding_score = 1.0 if audit.get("passed") else 0.0
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
    return sc
