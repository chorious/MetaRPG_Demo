"""Editor Agent — code-only RewriteTask generator (v0.6.4-era shape).

Not on the active turn path. In v0.6.6 the safety guarantee comes from
the parallel Safe Writers + decision tree, NOT from in-turn rewrites.
This module remains as a structured target for future repair loops:

  hard_audit issues -> list[RewriteTask] -> (consumer chooses how to apply)

`generate_rewrite_tasks` is pure code: it inspects the AuditIssue type
and emits one RewriteTask per issue, with the original `repair_instruction`
copied verbatim. The legacy `run_editor_rewrite` wrapper is retained for
backward-compat imports but returns the original WriterOutput unchanged
(no LLM call).
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.schemas import RewriteTask, WriterOutput


_OP_BY_TYPE: dict[str, str] = {
    "hidden_fact_leak":                 "replace",
    "absent_entity_action":             "delete",
    "remote_event_claim":               "delete",
    "raw_debug_exposure":               "replace",
    "invalid_effect_kind":              "replace",
    "npc_speech_without_patch_support": "replace",
    "npc_offer_without_patch_support":  "replace",
    "patch_without_support":            "replace",
    "state_change_without_support":     "replace",
    "schema_violation":                 "replace",
    "locked_fact_contradiction":        "delete",
    "unregistered_concrete_prop":       "replace",
}


def generate_rewrite_tasks(
    hard_issues: list[dict[str, Any]],
    medium_issues: list[dict[str, Any]] | None = None,
) -> list[RewriteTask]:
    """Convert hard/medium audit issues into segment-level rewrite tasks.

    The caller decides how to satisfy each task (LLM, code patch, manual).
    """
    tasks: list[RewriteTask] = []
    for issue in hard_issues or []:
        tasks.append(_issue_to_task(issue, severity="hard"))
    for issue in medium_issues or []:
        tasks.append(_issue_to_task(issue, severity="medium"))
    return tasks


def _issue_to_task(issue: dict[str, Any], severity: str) -> RewriteTask:
    type_ = issue.get("type", "")
    return RewriteTask(
        segment_id=issue.get("segment_id") or "",
        operation=_OP_BY_TYPE.get(type_, "replace"),
        severity=severity,
        reason=issue.get("reason", ""),
        keep_context_segments=[],
        allowed_patch_refs=[],
        instruction=issue.get("repair_instruction", ""),
    )


def run_editor_rewrite(
    original: WriterOutput,
    hard_issues: list[dict[str, Any]],
    feasibility_facts: list[str],
    client=None,
) -> WriterOutput:
    """Legacy entry point. v0.6.6: returns the original output unchanged.

    Repair has moved to parallel Safe Writers + decision tree. This stub
    exists so existing imports keep working without surprising side effects.
    """
    return original
