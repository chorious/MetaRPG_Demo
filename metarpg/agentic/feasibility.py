"""Feasibility Agent — local Qwen.

Lightweight pre-judgement on player input. Produces a FeasibilityReport
with facts, voice anchors, and the kind of world response that fits.

Restored 4-branch world_response_kind:
- absence:    the thing/target the player invoked doesn't exist in this world
- friction:   it exists but the world pushes back on the action
- reframing:  the action only makes sense if reinterpreted in-world
- accept:     proceed as stated (the default when in doubt)

Bold Writer ignores this report (runs in parallel). Safe Writers consume
feasibility_facts as soft constraints and route on world_response_kind.
On any LLM failure the report defaults to accept so Bold can carry the turn.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import FeasibilityReport


_SYSTEM_PROMPT = """You are the Feasibility Agent for a tabletop-RPG narrative engine.

Your job: read the player's free-text input and the local story packet,
and decide which kind of in-world response best fits the player's claim.

You do NOT write prose.
You do NOT give instructions to other agents.
You ONLY state facts, anchors, and pick one of four response kinds.

OUTPUT FIELDS

stated_action:
  one short verb-phrase describing what the player tried to do (in English or Chinese).

stated_props:
  list of the props/items the player explicitly invoked (lightsaber, key, cup, etc.).

stated_targets:
  list of the targets named or implied by the player (mara, the door, the well).

world_response_kind: one of
  "absence"    -> the prop or target doesn't exist in this world's schema
                  (lightsabers in a medieval tavern, an absent NPC)
  "friction"   -> the thing exists but the world resists the action
                  (door is locked, NPC won't speak, the action takes effort)
  "reframing"  -> the action only makes sense if reinterpreted in-world
                  (mind-reading -> reading body language; magic -> ritual)
  "accept"     -> the input is feasible as stated; no special response needed

feasibility_facts:
  flat list of short factual statements about what is or is not realizable
  in this world. State facts only — do NOT prescribe how the Writer should
  handle this. Examples:
    - "玩家声称使用'光剑',但此世界 schema 无此物（agrarian fantasy tavern）"
    - "Rusk 当前不在场（packet 中标记为 entities_not_present）"

preserve_player_voice:
  1–3 key words from the player input that the prose MUST preserve so we
  never silently substitute the player's intent. Usually the verb or noun
  the player used.

WORLD SCHEMA BOUNDARY (agrarian fantasy tavern, Greyfen village)

OUTSIDE this world:
- High-tech weapons (lightsabers, guns, laser swords, energy blades) -> absence
- Telepathy, mind-reading, psychic abilities -> reframing
- Modern technology (phones, electricity, vehicles) -> absence
- Sci-fi or space-fantasy elements -> absence

WHEN IN DOUBT -> "accept".
Do not invent constraints that are not in the packet.

FORMAT

Return exactly one valid JSON object, parseable by Python json.loads,
with no markdown fences and no commentary.
"""


_SCHEMA_VIOLATION_TERMS: dict[str, str] = {
    # term -> world_response_kind
    "光剑": "absence",
    "lightsaber": "absence",
    "激光剑": "absence",
    "能量剑": "absence",
    "手机": "absence",
    "电话": "absence",
    "电脑": "absence",
    "汽车": "absence",
    "枪": "absence",
    "心灵感应": "reframing",
    "读心": "reframing",
    "读心术": "reframing",
    "telepathy": "reframing",
    "mind reading": "reframing",
}


def _build_prompt(story_packet: dict[str, Any], player_input: str) -> str:
    return f"""STORY PACKET
{json.dumps(story_packet, ensure_ascii=False, indent=2)}

PLAYER INPUT
{player_input}

TASK
Judge the player's input. Pick one world_response_kind.

Return strict JSON:
{{
  "stated_action": "short verb phrase",
  "stated_props": ["..."],
  "stated_targets": ["..."],
  "world_response_kind": "absence" | "friction" | "reframing" | "accept",
  "feasibility_facts": ["fact 1", "fact 2"],
  "preserve_player_voice": ["key word 1", "key word 2"]
}}
"""


def _fallback_voice(player_input: str) -> list[str]:
    cleaned = player_input.strip().replace('"', " ").replace("'", " ")
    tokens = [t for t in cleaned.split() if t]
    if tokens:
        return tokens[:3]
    return [player_input[:6]] if player_input else []


def _deterministic_kind(player_input: str, story_packet: dict[str, Any]) -> tuple[str, list[str]]:
    """Cheap pre-filter for obvious schema violations.

    Returns (kind, facts). If no obvious match, kind == "" so the LLM (or
    accept default) decides.
    """
    lower = player_input.lower()
    facts: list[str] = []
    for term, kind in _SCHEMA_VIOLATION_TERMS.items():
        if term in player_input or term in lower:
            facts.append(f"玩家声称使用/调用 '{term}',但此世界 schema 不接受。")
            return kind, facts

    absent = set(story_packet.get("forbidden", {}).get("entities_not_present", []))
    for npc in absent:
        if npc and npc in player_input:
            facts.append(f"目标实体 '{npc}' 当前不在场。")
            return "absence", facts

    return "", facts


def _default_report(player_input: str, story_packet: dict[str, Any] | None = None) -> FeasibilityReport:
    """Safe optimistic default. Tries deterministic pre-filter, then accept."""
    voice = _fallback_voice(player_input)
    if story_packet is not None:
        kind, facts = _deterministic_kind(player_input, story_packet)
        if kind:
            return FeasibilityReport(
                feasibility_facts=facts,
                preserve_player_voice=voice,
                world_response_kind=kind,
            )
    return FeasibilityReport(
        feasibility_facts=[],
        preserve_player_voice=voice,
        world_response_kind="accept",
    )


_VALID_KINDS = {"absence", "friction", "reframing", "accept"}


def _coerce_kind(parsed: dict[str, Any]) -> str:
    """Pick a world_response_kind from possibly-old-shaped LLM output.

    Accepts either an explicit `world_response_kind` field (new) or a
    boolean `feasible` (old shape used by some tests/mocks) where
    feasible=False -> absence and feasible=True -> accept.
    """
    raw = parsed.get("world_response_kind")
    if isinstance(raw, str) and raw.strip().lower() in _VALID_KINDS:
        return raw.strip().lower()

    feas = parsed.get("feasible")
    if feas is False:
        return "absence"
    if feas is True:
        return "accept"
    return "accept"


def run_feasibility(
    story_packet: dict[str, Any],
    player_input: str,
    client: LlmClient | None = None,
) -> FeasibilityReport:
    """Call Feasibility LLM and parse output. Defaults to accept on any failure.

    Order of authority:
    1. If a client is provided and returns valid JSON, the LLM result wins.
    2. Else fall back to a deterministic pre-filter for obvious schema
       violations (lightsabers, telepathy, absent NPCs by name).
    3. Else default to accept.
    """
    if client is None:
        client = make_client("local")
    if client is None:
        return _default_report(player_input, story_packet)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_prompt(story_packet, player_input)},
    ]

    try:
        raw = client.chat(messages, temperature=0.2)
        parsed = _parse_json(raw)
    except Exception:
        return _default_report(player_input, story_packet)

    voice = parsed.get("preserve_player_voice", [])
    if not voice:
        voice = _fallback_voice(player_input)

    return FeasibilityReport(
        feasibility_facts=[str(f) for f in parsed.get("feasibility_facts", []) if f],
        preserve_player_voice=[str(v) for v in voice if v],
        world_response_kind=_coerce_kind(parsed),
        stated_action=str(parsed.get("stated_action", "") or ""),
        stated_props=[str(p) for p in parsed.get("stated_props", []) if p],
        stated_targets=[str(t) for t in parsed.get("stated_targets", []) if t],
    )


def _parse_json(text: str) -> dict[str, Any]:
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
        return json.loads(text[start : end + 1])

    raise ValueError(f"Feasibility output not JSON: {text[:200]!r}")
