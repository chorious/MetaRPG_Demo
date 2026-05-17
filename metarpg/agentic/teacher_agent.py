"""Teacher / Rule Curator — DeepSeek Pro.

Slow-path rule curator. Reviews recurring or severe issues and drafts
candidate rules + regression tests. Does NOT directly mutate hard_auditor.py.
"""
from __future__ import annotations

import json
import os
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import AuditIssue


_SYSTEM_PROMPT = """You are a rule curator for an RPG narrative engine.

Your job: review a batch of audit issues from recent turns and propose candidate rules.

You CANNOT directly modify source code.
You CANNOT auto-promote rules.
You CAN propose rules, test cases, and risk assessments.

Output STRICT JSON:
{
  "proposals": [
    {
      "proposal_id": "rule_hidden_inner_thought_v001",
      "problem_pattern": "...",
      "evidence_cases": ["turn_id_1", "turn_id_2"],
      "proposed_rule": {
        "scope": "narrative_claim_audit",
        "rule": "..."
      },
      "schema_change": null,
      "checker_change": {
        "claim_kind": "...",
        "condition": "...",
        "severity": "hard_fail"
      },
      "test_cases": [
        {
          "text": "...",
          "expected_claims": ["..."],
          "expected_result": "fail"
        }
      ],
      "risk": "...",
      "allowed_alternative": "..."
    }
  ]
}
"""


def run_teacher(
    issues: list[AuditIssue],
    turn_ids: list[str],
    client: LlmClient | None = None,
) -> list[dict[str, Any]]:
    """Analyze issues and propose candidate rules."""
    if client is None:
        client = make_client("pro")
    if client is None:
        return []

    # Only escalate severe or repeated issues
    severe = [i for i in issues if i.severity == "hard_fail"]
    if len(severe) < 2 and len(issues) < 3:
        return []

    prompt = f"""Recent turns: {json.dumps(turn_ids, ensure_ascii=False)}

Audit issues:
{json.dumps([{"severity": i.severity, "type": i.type, "reason": i.reason, "repair_instruction": i.repair_instruction} for i in issues], ensure_ascii=False, indent=2)}

Propose candidate rules to catch these patterns in the future.
"""

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_text = client.chat(messages, temperature=0.3)
        parsed = _parse_json_safe(raw_text)
    except Exception:
        return []

    return parsed.get("proposals", [])


def store_proposals(
    run_id: str,
    proposals: list[dict[str, Any]],
    base_dir: str = "runtime/agentic_runs",
) -> str:
    """Append proposals to session JSONL."""
    path = os.path.join(base_dir, run_id, "teacher_proposals.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for p in proposals:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return path


def _parse_json_safe(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
