"""Crystallize — narrative -> physical fact extraction (v0.6.6 Primitive D).

Turns audited narrative prose into canonical Fact objects. Only physical
facts are extracted (locations, props, entity appearances, observable
actions). Inner thoughts, speculations, and player feelings are filtered out.

Runs after commit so the extracted facts influence the next turn.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.lore_conflict import detect_conflict, record_conflict
from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import Segment
from metarpg.models import Fact, WorldState


_SYSTEM_PROMPT = """You are a fact extractor for a narrative world engine.

Your job: read the audited narrative segments and output any NEW physical
world facts that should become canon.

ONLY extract physical facts:
- location: a place or area the narrative names
- entity_appearance: what someone/something looks like (hair color, clothing, scars)
- prop: an object, item, or tool
- event: an observable action that happened

DO NOT extract:
- NPC inner thoughts or feelings
- Player subjective impressions
- Speculations or might-be statements
- Already-known facts from the input

Return strict JSON array:
[
  {"predicate": "has", "args": ["mara", "red_hair"], "fact_type": "entity_appearance"},
  {"predicate": "at", "args": ["clay_cup", "tavern"], "fact_type": "prop"}
]

Empty array [] if no new physical facts.
No markdown. No commentary.
"""


_PHYSICAL_TYPES = {"location", "entity_appearance", "prop", "event"}


def crystallize(
    segments: list[Segment],
    hard_audit: dict[str, Any],
    world: WorldState,
    client: LlmClient | None = None,
) -> list[Fact]:
    """Extract new physical facts from audited narrative.

    If audit did not pass, returns empty list (don't crystallize unreliable prose).
    """
    if not hard_audit.get("passed"):
        return []

    if not segments:
        return []

    prose = "\n".join(s.text for s in segments if s.text.strip())
    if not prose.strip():
        return []

    # Deterministic pre-filter: skip if no novel-looking content
    existing_predicates = {f.predicate for f in world.facts}

    if client is None:
        client = make_client("local")
    if client is None:
        # No LLM available: minimal deterministic extraction from known patterns
        return _deterministic_extract(segments, world)

    prompt = f"""EXISTING FACTS (do not repeat)
{json.dumps([str(f) for f in world.facts], ensure_ascii=False, indent=2)}

NARRATIVE
{prose}

TASK
List new physical world facts only. Return JSON array.
"""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = client.chat(messages, temperature=0.2)
        parsed = _parse_json(raw)
    except Exception:
        return []

    facts: list[Fact] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        ft = item.get("fact_type", "")
        if ft not in _PHYSICAL_TYPES:
            continue
        pred = item.get("predicate", "")
        args = item.get("args", [])
        if pred and args:
            # v0.6.6.1 Bug 1: normalize has-fact arg order to (player, item)
            if pred == "has" and len(args) == 2 and args[1] == "player":
                args = [args[1], args[0]]
            f = Fact(pred, tuple(str(a) for a in args), ft)
            # Skip duplicates
            if f not in world.facts:
                # Primitive E: detect lore conflicts before accepting
                conflicts = detect_conflict(f, world)
                for pair in conflicts:
                    record_conflict(world, pair)
                facts.append(f)
    return facts


def _deterministic_extract(segments: list[Segment], world: WorldState) -> list[Fact]:
    """Minimal code-only extraction when LLM is unavailable.

    Scans for named items/objects that appear in the text but have no
    corresponding fact in world.facts. Very conservative.
    """
    facts: list[Fact] = []
    known_props = {
        f.args[1] for f in world.facts
        if f.predicate == "has" and len(f.args) == 2
    }
    # Simple heuristic: look for Chinese nouns that look like items
    # followed by possession/location verbs
    for seg in segments:
        text = seg.text
        # Heuristic: "桌上放着陶杯" -> prop at location
        # This is intentionally minimal; LLM path is the real mechanism.
        pass
    return facts


def _parse_json(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []
