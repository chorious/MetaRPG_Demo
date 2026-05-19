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

import os
import time
import traceback
from statistics import median
from typing import Any

from metarpg.agentic import refusal_fallback
from metarpg.agentic.committer import commit_transaction, commit_turn
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
from metarpg.agentic.belief_tracker import update_beliefs_from_evidence
from metarpg.agentic.crystallize import crystallize
from metarpg.agentic.entity_lifecycle import tick_all_present
from metarpg.agentic.offscreen_tick import tick_offscreen_entities
from metarpg.agentic.time_flow import advance_time
from metarpg.agentic.translator_agent import run_translator
from metarpg.agentic.writer_agent import (
    WriterOutputError,
    run_writer,
    safe_mode_for_kind,
)

# v0.7.0 pipeline imports
from metarpg.agentic.director_agent import run_director
from metarpg.agentic.hook_manager import build_narrative_frame
from metarpg.agentic.motif_scheduler import schedule_motifs, update_motif_ledger
from metarpg.agentic.narrative_grammar import NarrativeGrammar, load_grammar
from metarpg.agentic.post_render_checker import check_rendered_prose
from metarpg.agentic.reference_resolver import resolve_references
from metarpg.agentic.render_brief import build_render_brief
from metarpg.agentic.render_repair import run_render_repair
from metarpg.agentic.renderer_agent import run_renderer
from metarpg.agentic.seed_loader import WorldSeed, load_seed
from metarpg.agentic.transaction import Commitment, NarrativeFrame, Operation, TurnTransaction
from metarpg.agentic.transaction_validator import validate_transaction


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

    # Primitive F: offscreen tick (before any Writer sees the world)
    tick_offscreen_entities(world, turn_index, client=local_client)

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
            player_input=player_input, client=flash_client,
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

    # Primitive D: crystallize — extract physical facts from narrative
    new_facts = crystallize(
        winner_output.segments, draft.hard_audit, world,
        client=local_client,
    )
    if new_facts:
        for f in new_facts:
            world.facts.add(f)
        if run_logger:
            run_logger.emit(
                turn_index, "crystallize", "facts_extracted",
                f"count={len(new_facts)}",
            )

    # Primitive C: belief tracker — update beliefs from player action evidence
    # Heuristic: if the narrative mentions a belief-related topic, nudge it.
    # (Full evidence mapping would require Translator to tag belief references.)
    # For now, placeholder: no automatic evidence without explicit tags.

    # Primitive A: advance time after every turn (even nothing_admitted)
    advance_time(world)

    # Primitive B: tick visible entities
    present = set(story_packet.get("scene", {}).get("visible_entities", []))
    tick_all_present(world, present)

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


def _to_dict(obj: Any) -> Any:
    """Serialize dataclass instances to plain dicts for JSON logging."""
    from dataclasses import asdict, is_dataclass
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _fallback_voice(player_input: str) -> list[str]:
    cleaned = player_input.strip().replace('"', " ").replace("'", " ")
    tokens = [t for t in cleaned.split() if t]
    return tokens[:3] if tokens else []


def _select_winner(
    candidates: dict[str, WriterOutput],
    audits: dict[str, dict[str, Any]],
    feasibility: FeasibilityReport,
    player_input: str = "",
    client=None,
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

    fallback_output = refusal_fallback.generate(
        feasibility,
        recent_player_input=player_input,
        client=client,
    )
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


# ---------------------------------------------------------------------------
# v0.7.0 Transaction-First Pipeline
# ---------------------------------------------------------------------------

_DEFAULT_SEED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "seeds", "dnd_ashen_vault_seed.yaml"
)
_DEFAULT_GRAMMAR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "narrative_grammar", "dnd_dungeon_grammar.yaml"
)


def run_agentic_turn_v070(
    *,
    world,
    player_input: str,
    turn_index: int,
    run_id: str,
    seed: WorldSeed | None = None,
    grammar: NarrativeGrammar | None = None,
    history: list[str] | None = None,
    run_logger=None,
) -> dict[str, Any]:
    """Run one complete v0.7.0 transaction-first turn.

    Pipeline:
      1. Story packet + feasibility -> player intent.
      2. Hook manager -> NarrativeFrame.
      3. Director (local vLLM) -> TurnTransaction.
      4. Validator -> accepted / downgraded / rejected.
      5. Committer -> updated WorldState.
      6. RenderBrief + Renderer (DeepSeek Flash) -> Chinese prose.
      7. Post-render checker -> pass / repaired / failed.
      8. Primitives: advance_time, tick entities.
    """
    if history is None:
        history = []

    turn_start = time.perf_counter()
    draft_id = f"{run_id}_turn_{turn_index:03d}"

    if run_logger:
        run_logger.emit(turn_index, "turn", "turn_start_v070", player_input)

    # Load defaults if caller did not provide seed/grammar
    if seed is None:
        seed = load_seed(_DEFAULT_SEED_PATH)
    if grammar is None:
        grammar = load_grammar(_DEFAULT_GRAMMAR_PATH)

    # 1. Story packet ---------------------------------------------------------
    story_packet = build_story_packet(world)
    if run_logger:
        run_logger.emit(turn_index, "story_packet", "story_packet_built")

    flash_client = make_client("flash")
    local_client = make_client("local")

    # Primitive F: offscreen tick
    tick_offscreen_entities(world, turn_index, client=local_client)

    # 2. Feasibility -> player intent -----------------------------------------
    feas_result = run_feasibility(story_packet, player_input, client=local_client)
    if run_logger:
        run_logger.emit(turn_index, "feasibility", "feasibility_complete")

    # v0.7.2: L1 Reference Resolution — known_universe + available_universe
    aliases_map = _build_aliases_map(seed)
    scene = story_packet.get("scene", {})
    player_ctx = story_packet.get("player_context", {})
    player_location = scene.get("location", "")
    reachable_locs = [
        loc for loc in seed.locations
        if _location_reachable(loc, player_location, seed)
    ]
    visible_objs = scene.get("visible_objects", [])
    last_targets = getattr(world, "_last_resolved_targets", [])
    resolved_intent = resolve_references(
        player_input=player_input,
        known_entities=list(seed.entities.keys()),
        known_items=list(seed.items.keys()),
        known_locations=list(seed.locations.keys()),
        known_hooks=list(seed.active_hooks.keys()),
        known_motifs=list(seed.motifs.keys()),
        available_entities=scene.get("visible_entities", []),
        available_items=[i for i in seed.items if i in visible_objs],
        available_locations=reachable_locs,
        available_hooks=list(seed.active_hooks.keys()),
        available_motifs=list(seed.motifs.keys()),
        aliases_map=aliases_map,
        client=local_client,
        last_targets=last_targets,
        player_location=player_location,
    )
    # Store for next turn's coreference resolution
    world._last_resolved_targets = list(resolved_intent.targets) + list(resolved_intent.props)
    if run_logger:
        run_logger.emit(
            turn_index, "reference_resolver", "intent_resolved",
            f"targets={[r.canonical_id for r in resolved_intent.targets]} "
            f"props={[r.canonical_id for r in resolved_intent.props]}"
        )
        run_logger.emit_artifact(
            turn_index, "resolved_intent",
            _to_dict(resolved_intent),
        )

    # Build canonical ID whitelist for Director
    canonical_id_whitelist = {
        "reachable_location_ids": reachable_locs,
        "visible_entity_ids": scene.get("visible_entities", []),
        "active_hook_ids": list(seed.active_hooks.keys()),
        "allowed_motif_ids": list(seed.motifs.keys()),
    }

    # 3. NarrativeFrame -------------------------------------------------------
    narrative_frame = build_narrative_frame(
        player_input, resolved_intent, seed, grammar, world, client=local_client
    )
    narrative_frame.canonical_id_whitelist = canonical_id_whitelist
    narrative_frame.resolved_targets = [
        {"mention": r.mention, "canonical_id": r.canonical_id, "kind": r.kind, "confidence": r.confidence, "available": r.available}
        for r in resolved_intent.targets
    ]
    narrative_frame.resolved_props = [
        {"mention": r.mention, "canonical_id": r.canonical_id, "kind": r.kind, "confidence": r.confidence, "available": r.available}
        for r in resolved_intent.props
    ]
    narrative_frame.unresolved_mentions = resolved_intent.unresolved

    # v0.7.1: Motif scheduling
    motif_schedule = schedule_motifs(
        beat=narrative_frame.beat,
        active_hooks=narrative_frame.active_hooks,
        seed=seed,
        grammar=grammar,
        motif_ledger=getattr(world, "motif_ledger", {}),
        current_turn=getattr(world, "turn", 0),
    )
    narrative_frame.motifs_to_use = motif_schedule.motifs_to_use

    if run_logger:
        run_logger.emit_artifact(
            turn_index, "motif_schedule",
            {
                "motifs_to_use": motif_schedule.motifs_to_use,
                "debug": motif_schedule.debug,
            },
        )
        run_logger.emit(turn_index, "frame", "frame_built", narrative_frame.beat)
        run_logger.emit_artifact(
            turn_index, "narrative_frame",
            _to_dict(narrative_frame),
        )

    # v0.7.3: Deterministic Movement Path ----------------------------------
    move_target = _resolve_move_target(resolved_intent, reachable_locs)
    absent_refs = [r for r in resolved_intent.targets if not r.available]
    if move_target:
        tx = _build_deterministic_move_tx(
            player_input, move_target, narrative_frame, draft_id
        )
        if run_logger:
            run_logger.emit(
                turn_index, "director", "deterministic_movement",
                f"destination={move_target}"
            )
            run_logger.emit_artifact(
                turn_index, "transaction_raw",
                {
                    "note": "deterministic_movement (no Director call)",
                    "parsed": _to_dict(tx),
                },
            )
    # v0.7.2: Absence Response — known-but-unavailable target + interact action
    elif absent_refs and resolved_intent.action_type in ("ask", "speak", "interact"):
        tx = _build_absence_response(player_input, narrative_frame, absent_refs, draft_id)
        if run_logger:
            run_logger.emit(
                turn_index, "director", "absence_response",
                f"absent={','.join(r.canonical_id for r in absent_refs)}"
            )
            run_logger.emit_artifact(
                turn_index, "transaction_raw",
                {"note": "absence_response (no Director call)", "parsed": _to_dict(tx)},
            )
    else:
        # 4. Director -> TurnTransaction --------------------------------------
        tx = run_director(
            player_input, narrative_frame, story_packet, client=local_client, max_retries=1
        )
        # Enrich tx with frame/id so downstream can use them if needed
        tx.id = draft_id
        tx.narrative_frame = narrative_frame
        tx.player_intent = {"action_type": resolved_intent.action_type, "unresolved": resolved_intent.unresolved}
        if run_logger:
            run_logger.emit(
                turn_index, "director", "transaction_produced",
                f"ops={len(tx.operations)} commits={len(tx.commitments)}"
            )
            run_logger.emit_artifact(
                turn_index, "transaction_raw",
                {
                    "director_raw_output": getattr(tx, "_director_raw", None),
                    "parsed": _to_dict(tx),
                },
            )

    # 5. Validator ------------------------------------------------------------
    val_result = validate_transaction(tx, world, grammar=grammar.__dict__, client=local_client)
    if run_logger:
        run_logger.emit(
            turn_index, "validator", val_result.status,
            f"issues={len(val_result.issues)} downgrades={len(val_result.downgrades)}"
        )
        run_logger.emit_artifact(
            turn_index, "transaction_validated",
            {
                "status": val_result.status,
                "transaction": _to_dict(tx),
                "issues": _to_dict(val_result.issues),
                "downgrades": _to_dict(val_result.downgrades),
            },
        )

    if val_result.status == "rejected":
        tx = _v070_fallback_tx(player_input, narrative_frame)
        if run_logger:
            run_logger.emit(turn_index, "validator", "fallback_activated", "rejected")
    elif val_result.transaction is not None:
        tx = val_result.transaction

    # 6. Commit ---------------------------------------------------------------
    commit_result = commit_transaction(world, tx)
    if run_logger:
        run_logger.emit(
            turn_index, "commit", "commit_success",
            f"turn={commit_result['turn']}"
        )

    # v0.7.1: update motif ledger
    if not hasattr(world, "motif_ledger"):
        world.motif_ledger = {}
    if motif_schedule.motifs_to_use:
        world.motif_ledger = update_motif_ledger(
            world.motif_ledger, motif_schedule, world.turn
        )

    # 7. RenderBrief ----------------------------------------------------------
    render_brief = build_render_brief(tx, narrative_frame, world)
    if run_logger:
        run_logger.emit_artifact(
            turn_index, "render_brief",
            _to_dict(render_brief),
        )

    # 8. Renderer (DeepSeek Flash) --------------------------------------------
    try:
        prose = run_renderer(render_brief, story_packet, client=flash_client)
    except Exception as exc:
        prose = "……"  # Minimal safe fallback
        if run_logger:
            run_logger.log_error(turn_index, "renderer", type(exc).__name__, str(exc))

    # 9. Post-render checker --------------------------------------------------
    check_result = check_rendered_prose(prose, tx, world, client=local_client)

    # v0.7.3: L2 Repair Loop — attempt one-shot repair if failed
    if check_result["status"] == "failed":
        try:
            repaired_prose = run_render_repair(
                prose,
                check_result["issues"],
                check_result.get("semantic_judgments", []),
                render_brief,
                client=flash_client,
            )
            re_check = check_rendered_prose(repaired_prose, tx, world, client=local_client)
            if re_check["status"] == "pass":
                prose = repaired_prose
                check_result = {
                    "status": "repaired",
                    "issues": re_check.get("issues", []),
                    "semantic_judgments": re_check.get("semantic_judgments", []),
                    "repair_attempted": True,
                    "repair_success": True,
                }
            else:
                check_result["repair_attempted"] = True
                check_result["repair_success"] = False
        except Exception as exc:
            # Repair call failure is non-blocking
            check_result["repair_attempted"] = True
            check_result["repair_error"] = str(exc)

    if run_logger:
        run_logger.emit(
            turn_index, "post_render", check_result["status"],
            str(check_result["issues"]) if check_result["issues"] else "clean"
        )
        run_logger.emit_artifact(
            turn_index, "post_render",
            dict(check_result),
        )
        run_logger.emit_artifact(
            turn_index, "semantic_judgments",
            {
                "judgments": check_result.get("semantic_judgments", []),
                "l2_ran": bool(check_result.get("semantic_judgments")),
            },
        )

    # 10. Primitives ----------------------------------------------------------
    advance_time(world)
    present = set(story_packet.get("scene", {}).get("visible_entities", []))
    tick_all_present(world, present)

    turn_wall_time = time.perf_counter() - turn_start

    l2_checks_run = 1 if check_result.get("semantic_judgments") else 0

    return {
        "draft_id": draft_id,
        "player_input": player_input,
        "narrative_frame": narrative_frame,
        "transaction": tx,
        "validation": val_result,
        "commit": commit_result,
        "player_output": prose,
        "post_render": check_result,
        "committed": True,
        "error": None,
        "turn_wall_time_s": turn_wall_time,
        "l2_checks_run": l2_checks_run,
    }


def _feasibility_to_intent(feas: FeasibilityReport, player_input: str = "") -> dict[str, Any]:
    """Map FeasibilityReport fields to the player_intent dict HookManager expects."""
    action = feas.stated_action or "ambiguous"
    action_type = "ambiguous"

    # English verb map
    _VERB_MAP: dict[str, str] = {
        "inspect": "inspect", "check": "inspect", "examine": "inspect",
        "ask": "ask", "question": "ask", "talk": "ask",
        "help": "help", "aid": "help",
        "move": "move", "go": "move", "approach": "move", "walk": "move",
        "take": "take", "pick": "take", "grab": "take",
        "give": "give", "hand": "give",
        "wait": "wait", "rest": "wait",
        "attack": "attack", "fight": "attack", "hit": "attack",
    }

    for verb, atype in _VERB_MAP.items():
        if verb in action.lower():
            action_type = atype
            break

    # Fallback: Chinese keyword map from raw player_input
    if action_type == "ambiguous" and player_input:
        _CN_VERBS: dict[str, str] = {
            "检查": "inspect", "查看": "inspect", "观察": "inspect", "检视": "inspect",
            "问": "ask", "询问": "ask", "打听": "ask", "谈": "ask",
            "帮助": "help", "帮": "help", "协助": "help", "救": "help",
            "走": "move", "去": "move", "移动": "move", "接近": "move", "靠近": "move",
            "拿": "take", "取": "take", "捡起": "take", "抓": "take",
            "给": "give", "递": "give", "交": "give",
            "等待": "wait", "等": "wait", "休息": "wait",
            "攻击": "attack", "打": "attack", "杀": "attack", "砍": "attack",
        }
        for cn, atype in _CN_VERBS.items():
            if cn in player_input:
                action_type = atype
                action = cn
                break

    return {
        "action_type": action_type,
        "action": action,
        "targets": feas.stated_targets or [],
        "props": feas.stated_props or [],
        "world_response_kind": feas.world_response_kind,
    }


def _build_aliases_map(seed: WorldSeed) -> dict[str, list[str]]:
    """Build a flat map of canonical_id -> alias phrases from seed."""
    aliases_map: dict[str, list[str]] = {}
    for cid, loc in seed.locations.items():
        aliases_map[cid] = loc.get("aliases", [])
    for cid, ent in seed.entities.items():
        aliases_map[cid] = ent.get("aliases", [])
    for cid, item in seed.items.items():
        aliases_map[cid] = item.get("aliases", [])
    for cid, hook in seed.active_hooks.items():
        aliases_map[cid] = hook.get("aliases", [])
    for cid, motif in seed.motifs.items():
        aliases_map[cid] = motif.get("aliases", [])
    return aliases_map


def _location_reachable(loc_id: str, player_loc: str, seed: WorldSeed) -> bool:
    """Check if a location is reachable from the player's current location."""
    if loc_id == player_loc:
        return True
    current = seed.locations.get(player_loc, {})
    exits = current.get("exits", [])
    return loc_id in exits


def _resolve_move_target(
    resolved_intent,
    reachable_locs: list[str],
) -> str | None:
    """Check if this intent qualifies for deterministic movement.

    Returns the target location canonical_id, or None.
    """
    if resolved_intent.action_type != "move":
        return None
    if len(resolved_intent.targets) != 1:
        return None
    target = resolved_intent.targets[0]
    if target.kind != "location":
        return None
    if not target.available:
        return None
    if target.canonical_id not in reachable_locs:
        return None
    return target.canonical_id


def _build_deterministic_move_tx(
    player_input: str,
    target_id: str,
    frame: NarrativeFrame,
    draft_id: str = "",
) -> TurnTransaction:
    """Deterministic transaction for a simple, valid player movement."""
    desc = f"Player moves to {target_id.replace('_', ' ')}."
    return TurnTransaction(
        id=draft_id,
        player_input=player_input,
        narrative_frame=frame,
        operations=[
            Operation("move_player", {"destination": target_id, "description": desc}),
            Operation("add_event", {"summary": desc}),
        ],
        commitments=[
            Commitment("canon", desc, operation_index=0),
            Commitment("event", desc, operation_index=1),
        ],
        assumptions=[
            {
                "source": "deterministic_movement",
                "reason": f"action_type=move, target={target_id} is reachable",
            }
        ],
    )


def _build_absence_response(
    player_input: str,
    frame: NarrativeFrame,
    absent_refs: list,
    draft_id: str = "",
) -> TurnTransaction:
    """Deterministic transaction when player refers to a known-but-absent target.

    v0.7.2: Skips Director; output still flows through RenderBrief + Flash Renderer.
    """
    from metarpg.agentic.transaction import Commitment, Operation

    names = ", ".join(r.canonical_id.replace("_", " ") for r in absent_refs)
    desc = f"You look around, but {names} is not here."

    return TurnTransaction(
        id=draft_id,
        player_input=player_input,
        narrative_frame=frame,
        operations=[
            Operation("observe_reaction", {"entity": "player", "description": desc}),
            Operation("add_event", {"summary": f"Player attempts to interact with absent target: {names}"}),
        ],
        commitments=[
            Commitment("texture", f"Moment of confusion — {names} absent.", operation_index=0),
        ],
        assumptions=[
            {
                "source": "absence_response",
                "reason": f"{','.join(r.canonical_id for r in absent_refs)} not in visible_entities",
            }
        ],
    )


def _v070_fallback_tx(player_input: str, frame: NarrativeFrame) -> TurnTransaction:
    """Deterministic fallback when validation rejects a transaction."""
    from metarpg.agentic.transaction import Commitment, Operation
    return TurnTransaction(
        player_input=player_input,
        narrative_frame=frame,
        operations=[
            Operation("inner_monologue", {"text": "Player hesitates."}),
            Operation("add_texture", {"text": "The moment hangs in the air."}),
        ],
        commitments=[
            Commitment(
                "texture",
                "A brief pause before action.",
                operation_index=1,
            )
        ],
        assumptions=[
            {"source": "fallback", "reason": "Validation rejected original transaction"}
        ],
    )
