"""Soft Auditor Agent — local Qwen3.6.

Checks what code cannot easily judge:
- Does the text feel like player-facing RPG prose?
- Does it expose debug concepts?
- Is emotional intensity proportional to patch effects?
- Is the NPC reaction too certain given weak evidence?
- Does the scene repeat prior beats unnaturally?
- Does the narrative imply more than the patch says?
- Is the story vivid but still grounded?
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import AuditIssue, Segment


_SYSTEM_PROMPT = """You are a prose quality auditor for an RPG narrative engine.

Your job: review player-facing narrative segments and flag quality issues.

You CANNOT invent new plot.
You CANNOT commit changes.
You CANNOT override hard failures.

Issue types (closed set):
- too_mechanical: reads like a status report, not prose
- debug_tone: uses game terms, probabilities, or system concepts
- repetition: repeats a beat from recent history without variation
- overdramatized_reaction: NPC reacts too strongly to minor action
- underspecified_feedback: player action gets no meaningful consequence cue
- style_drift: tone shifts abruptly between segments
- weak_player_feedback: player does something but narrative feels hollow

Output STRICT JSON:
{
  "issues": [
    {
      "type": "issue_type",
      "segment_id": "s1",
      "evidence": "quoted text",
      "reason": "why this is a problem",
      "repair_instruction": "how to fix"
    }
  ]
}
"""


def _build_prompt(
    segments: list[Segment],
    recent_history: list[str],
    admitted_patch: list[dict[str, Any]],
) -> str:
    return f"""Recent player history:
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

Segments to review:
{json.dumps([{"id": s.id, "type": s.type, "text": s.text} for s in segments], ensure_ascii=False, indent=2)}

Admitted patch effects:
{json.dumps(admitted_patch, ensure_ascii=False, indent=2)}

Review each segment for prose quality and tonal consistency.
"""


def run_soft_auditor(
    segments: list[Segment],
    recent_history: list[str],
    admitted_patch: list[dict[str, Any]],
    client: LlmClient | None = None,
) -> list[AuditIssue]:
    if client is None:
        client = make_client("local")
    if client is None:
        return []

    prompt = _build_prompt(segments, recent_history, admitted_patch)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_text = client.chat(messages, temperature=0.4)
        parsed = _parse_json_safe(raw_text)
    except Exception:
        return []

    issues: list[AuditIssue] = []
    for i in parsed.get("issues", []):
        issues.append(
            AuditIssue(
                severity="soft_issue",
                type=i.get("type", ""),
                segment_id=i.get("segment_id"),
                evidence=i.get("evidence", ""),
                reason=i.get("reason", ""),
                repair_instruction=i.get("repair_instruction", ""),
            )
        )
    return issues


def _parse_json_safe(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
