"""Repair loop — bounded rewrite orchestration.

Limits:
- max_repair_rounds = 2
- max_writer_calls_per_turn = 3
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.schemas import (
    AuditIssue,
    CandidatePatchEffect,
    RewriteTask,
    Segment,
    TurnDraft,
    WriterOutput,
)
from metarpg.agentic.writer_agent import run_writer
from metarpg.agentic.editor_agent import run_editor


MAX_REPAIR_ROUNDS = 2
MAX_WRITER_CALLS = 3


def run_repair_loop(
    draft: TurnDraft,
    story_packet: dict[str, Any],
    hard_issues: list[AuditIssue],
    soft_issues: list[AuditIssue],
    writer_client: Any | None = None,
    editor_client: Any | None = None,
) -> TurnDraft:
    """Attempt to repair failing segments locally."""
    if not hard_issues and not soft_issues:
        draft.final_segments = list(draft.writer_output.segments) if draft.writer_output else []
        draft.admitted_patch = list(draft.candidate_patch)
        return draft

    all_issues = hard_issues + soft_issues
    writer_calls = 1  # initial call already made

    for round_idx in range(MAX_REPAIR_ROUNDS):
        if writer_calls >= MAX_WRITER_CALLS:
            break

        # Generate rewrite tasks
        tasks = run_editor(
            draft.writer_output.segments if draft.writer_output else [],
            all_issues,
            [e.__dict__ for e in draft.admitted_patch],
            client=editor_client,
        )

        if not tasks:
            break

        draft.editor_tasks.extend(tasks)

        # Determine if patch needs changing
        patch_failed = any(i.severity == "hard_fail" for i in hard_issues)

        if patch_failed and draft.writer_output:
            # Rewrite affected segments + patch
            writer_calls += 1
            try:
                new_output = run_writer(story_packet, draft.player_input, client=writer_client)
            except Exception:
                break

            draft.rewrite_history.append({
                "round": round_idx,
                "mode": "patch+narrative",
                "tasks": [t.__dict__ for t in tasks],
                "prior_segments": [s.__dict__ for s in draft.writer_output.segments],
            })
            draft.writer_output = new_output
            draft.candidate_patch = list(new_output.candidate_patch)
        else:
            # Narrative-only repair: keep patch, rewrite segments
            # For mock/Phase F, we accept the original and note repair needed
            draft.rewrite_history.append({
                "round": round_idx,
                "mode": "narrative-only",
                "tasks": [t.__dict__ for t in tasks],
            })
            # In full implementation, would call a narrative-only rewriter here
            break

    # Finalize
    if draft.writer_output:
        draft.final_segments = list(draft.writer_output.segments)
    draft.admitted_patch = list(draft.candidate_patch)
    return draft
