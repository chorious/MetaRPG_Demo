"""Translator Agent — local Qwen3.6.

Extracts narrative claims from Writer segments.
Only answers: "What does this text claim happened?"
Does NOT answer: "Is this allowed?"
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import NarrativeClaim, Segment


_SYSTEM_PROMPT = """You are a narrative claim extractor for an RPG engine.

Your job: read each segment of player-facing narrative and extract explicit claims.

Claim kinds (closed set):
- player_action
- player_speech
- player_memory_or_journal
- npc_speech
- npc_offer
- npc_observable_action
- npc_observable_reaction
- npc_inner_state
- ambient_entity_action        # unnamed background entities (e.g. tavern crowd)
- named_entity_action          # specific named NPC acts
- entity_present_action        # legacy alias for named_entity_action
- object_state
- location_state
- prop_usage                   # player uses a concrete item
- unregistered_prop_usage      # item not in inventory/visible_objects
- knowledge_claim
- hidden_fact_reference
- world_state_change
- concrete_affordance_creation # NPC creates a new interaction opportunity
- uncertain_inference
- remote_event
- raw_debug_exposure

Rules:
- Over-extract rather than under-extract.
- Do NOT merge multiple events into one claim.
- Every claim MUST have an evidence_span quoting the exact text it is based on.
- If text implies inner knowledge, extract npc_inner_state or knowledge_claim.
- If text mentions hidden facts or secrets, extract hidden_fact_reference.
- If text describes unnamed background entities, extract ambient_entity_action.
- If an NPC makes an offer or creates a new interaction opportunity, extract npc_offer or concrete_affordance_creation.
- Output STRICT JSON.
"""


def _build_prompt(segments: list[Segment], story_packet: dict[str, Any]) -> str:
    seg_text = json.dumps(
        [
            {"id": s.id, "type": s.type, "text": s.text}
            for s in segments
        ],
        ensure_ascii=False,
        indent=2,
    )
    forbidden = json.dumps(story_packet.get("forbidden", {}), ensure_ascii=False, indent=2)
    return f"""Segments to analyze:
{seg_text}

Forbidden mentions (flag if any segment violates):
{forbidden}

For each segment, output claims as JSON:
{{
  "claims": [
    {{
      "segment_id": "s1",
      "kind": "claim_kind",
      "subject": "entity or null",
      "action": "verb or null",
      "target": "entity or null",
      "evidence_span": "exact quoted text from segment",
      "confidence": 0.92
    }}
  ]
}}
"""


def run_translator(
    segments: list[Segment],
    story_packet: dict[str, Any],
    client: LlmClient | None = None,
) -> list[NarrativeClaim]:
    """Call Translator LLM and return extracted claims."""
    if client is None:
        client = make_client("local")
    if client is None:
        raise RuntimeError("Translator LLM client unavailable (check set.env)")

    prompt = _build_prompt(segments, story_packet)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    raw_text = client.chat(messages, temperature=0.3)
    parsed = _parse_json_safe(raw_text)

    claims: list[NarrativeClaim] = []
    for c in parsed.get("claims", []):
        claims.append(
            NarrativeClaim(
                segment_id=c.get("segment_id", ""),
                kind=c.get("kind", ""),
                subject=c.get("subject"),
                action=c.get("action"),
                target=c.get("target"),
                evidence_span=c.get("evidence_span", ""),
                confidence=c.get("confidence", 0.0),
            )
        )
    return claims


def _parse_json_safe(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
