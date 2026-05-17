"""Editor Agent — local Qwen3.6.

Creates localized rewrite tasks (not prose directly).
Preserves passing segments.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import AuditIssue, RewriteTask, Segment


_SYSTEM_PROMPT = """You are a repair editor for an RPG narrative engine.

Your job: given failing audit issues, produce localized rewrite tasks.

Rules:
- Prefer local repair over full rewrite.
- Preserve passing segments. Do not touch them.
- Do not alter admitted patch unless patch itself failed.
- If patch failed, request patch + affected segment rewrite.
- If only prose failed, request narrative-only rewrite.
- Output STRICT JSON rewrite tasks.

Allowed operations: replace, delete, insert_after
"""


def _build_prompt(
    segments: list[Segment],
    issues: list[AuditIssue],
    admitted_patch: list[dict[str, Any]],
) -> str:
    return f"""Current segments:
{json.dumps([{"id": s.id, "type": s.type, "text": s.text} for s in segments], ensure_ascii=False, indent=2)}

Audit issues:
{json.dumps([{"severity": i.severity, "type": i.type, "segment_id": i.segment_id, "reason": i.reason, "repair_instruction": i.repair_instruction} for i in issues], ensure_ascii=False, indent=2)}

Admitted patch:
{json.dumps(admitted_patch, ensure_ascii=False, indent=2)}

Produce rewrite tasks as JSON:
{{
  "rewrite_tasks": [
    {{
      "segment_id": "s1",
      "operation": "replace",
      "severity": "hard_fail",
      "reason": "...",
      "keep_context_segments": ["s0"],
      "allowed_patch_refs": ["observe_reaction:mara:brief_notice"],
      "instruction": "Rewrite this segment as external observable reaction only."
    }}
  ]
}}
"""


def run_editor(
    segments: list[Segment],
    issues: list[AuditIssue],
    admitted_patch: list[dict[str, Any]],
    client: LlmClient | None = None,
) -> list[RewriteTask]:
    if client is None:
        client = make_client("local")
    if client is None:
        return []

    prompt = _build_prompt(segments, issues, admitted_patch)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_text = client.chat(messages, temperature=0.3)
        parsed = _parse_json_safe(raw_text)
    except Exception:
        return []

    tasks: list[RewriteTask] = []
    for t in parsed.get("rewrite_tasks", []):
        tasks.append(
            RewriteTask(
                segment_id=t.get("segment_id", ""),
                operation=t.get("operation", "replace"),
                severity=t.get("severity", "soft_issue"),
                reason=t.get("reason", ""),
                keep_context_segments=t.get("keep_context_segments", []),
                allowed_patch_refs=t.get("allowed_patch_refs", []),
                instruction=t.get("instruction", ""),
            )
        )
    return tasks


def _parse_json_safe(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
