"""Writer Agent — DeepSeek Flash.

Interprets player action in local context and writes segmented player-facing
narrative with candidate patch effects.

Uses prompt from MetaRPG_Agent_story_prompt_reference.md §2-3.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import CandidatePatchEffect, Segment, WriterOutput


class WriterOutputError(RuntimeError):
    """Raised when Writer output cannot be parsed, with raw text preserved."""

    def __init__(self, message: str, raw_text: str = "") -> None:
        super().__init__(message)
        self.raw_text = raw_text


_SYSTEM_PROMPT = """You are the Writer Agent for MetaRPG.

You write vivid, player-facing local adventure prose.
You are not the final authority on world state.
You propose candidate patch effects, assumptions, and segmented narrative.
The Committer decides what becomes canon after audit.

Your job:
1. Interpret the player's action in the given local story packet.
2. Write short, vivid narrative segments.
3. Propose candidate patch effects using only allowed effect kinds.
4. Declare assumptions explicitly.
5. Keep player-facing prose free of raw event ids, debug terms, belief percentages, and schema language.

Hard constraints:
- Do not let absent entities act, watch, speak, or react.
- Do not describe NPC inner thoughts as fact.
- Do not expose hidden facts unless allowed_reveals explicitly permits it.
- Do not invent new named NPCs, locations, objects, or hard facts unless candidate_patch includes an allowed effect for doing so.
- Do not make hard state changes only in prose.
- Every meaningful story segment must either reference candidate patch effects or be marked as pure sensory/transient.
- Keep the final narrative grounded in what the player can observe.

Style:
- Chinese prose.
- 1 to 4 short segments per turn.
- Concrete sensory detail is good.
- Do not over-explain trust, belief, probability, or system reasoning.
- Let mystery remain mystery.
"""


def _build_prompt(story_packet: dict[str, Any], player_input: str) -> str:
    return f"""STORY PACKET
{json.dumps(story_packet, ensure_ascii=False, indent=2)}

PLAYER INPUT
{player_input}

TASK
Write a local turn draft.

Return strict JSON only.

Required output schema:
{{
  "interpretation": "Plain-language interpretation of the player's action.",
  "segments": [
    {{
      "id": "s1",
      "type": "player_action | sensory | npc_observable_reaction | npc_speech | journal | transition",
      "text": "Player-facing Chinese prose.",
      "patch_refs": ["effect_kind:target_or_id"],
      "declared_claims": ["claim-like plain strings"],
      "transient_only": false
    }}
  ],
  "candidate_patch": [
    {{
      "kind": "transient_event | journal_note | observe_reaction | knowledge_transfer | relation_delta | belief_delta | move | add_fact | remove_fact | create_hook | consume_item | acquire_item | risk_flag | reveal",
      "args": {{}}
    }}
  ],
  "assumptions": [
    {{
      "claim": "What assumption you used.",
      "basis": "Where in the story packet this came from."
    }}
  ],
  "risk_notes": [
    "Any uncertainty or boundary you noticed."
  ]
}}

Do not include markdown.
Do not include explanations outside JSON.
"""


def run_writer(
    story_packet: dict[str, Any],
    player_input: str,
    client: LlmClient | None = None,
) -> WriterOutput:
    """Call Writer LLM and parse output."""
    if client is None:
        client = make_client("flash")
    if client is None:
        raise RuntimeError("Writer LLM client unavailable (check set.env)")

    prompt = _build_prompt(story_packet, player_input)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    raw_text = client.chat(messages, temperature=0.7)
    try:
        parsed = _parse_json_safe(raw_text)
    except Exception as exc:
        raise WriterOutputError(str(exc), raw_text=raw_text) from exc

    segments = []
    for seg_data in parsed.get("segments", []):
        segments.append(
            Segment(
                id=seg_data.get("id", ""),
                type=seg_data.get("type", ""),
                text=seg_data.get("text", ""),
                patch_refs=seg_data.get("patch_refs", []),
                declared_claims=seg_data.get("declared_claims", []),
                transient_only=seg_data.get("transient_only", False),
            )
        )

    candidate_patch = []
    for eff_data in parsed.get("candidate_patch", []):
        candidate_patch.append(
            CandidatePatchEffect(
                kind=eff_data.get("kind", ""),
                args=eff_data.get("args", {}),
            )
        )

    return WriterOutput(
        interpretation=parsed.get("interpretation", ""),
        segments=segments,
        candidate_patch=candidate_patch,
        assumptions=parsed.get("assumptions", []),
        risk_notes=parsed.get("risk_notes", []),
        raw_json=parsed,
    )


def _parse_json_safe(text: str) -> dict[str, Any]:
    """Strip common wrappers and parse the first JSON object.

    Live LLMs occasionally add prose before/after the object, or return fenced
    JSON with whitespace around the fence. Keep this parser permissive while
    making failures diagnosable.
    """
    original = text
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            snippet = original[:800].replace("\n", "\\n")
            raise ValueError(f"Writer returned invalid JSON: {exc}. raw_prefix={snippet}") from exc

    snippet = original[:800].replace("\n", "\\n")
    raise ValueError(f"Writer returned no JSON object. raw_prefix={snippet}")
