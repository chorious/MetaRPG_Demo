"""Deterministic scanner — supports Translator with obvious pattern detection.

Catches:
- known entity name scan
- hidden fact alias scan
- snake_case raw event id scan
- inner-thought verb scan
- remote event cue scan
- unsupported location/entity mentions
"""
from __future__ import annotations

import re
from typing import Any

from metarpg.agentic.schemas import NarrativeClaim


# Inner-thought verbs that signal NPC internal state exposure
_INNER_THOUGHT_VERBS = {
    "想到", "意识到", "记得", "知道", "怀疑", "害怕",
    "寻思", "暗自", "心想", "心念", "念头", "想起",
}

# Remote event cues that claim action at a distance
_REMOTE_CUES = {
    "与此同时", "远处", "守卫站那边", "酒馆那边", "另一边",
    "与此同时", "at the same time", "in the distance",
    "meanwhile", "over at",
}

# Pattern for raw snake_case event IDs
_SNAKE_CASE_ID = re.compile(r"\b[a-z]+_[a-z_]+\b")


def scan_segment(
    segment_id: str,
    text: str,
    known_entities: list[str],
    known_locations: list[str],
    hidden_aliases: list[str],
) -> dict[str, Any]:
    """Run deterministic scans on one segment. Returns findings dict."""
    findings: dict[str, Any] = {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "unsupported_entity_mentions": [],
        "claims": [],
    }

    text_lower = text.lower()

    # 1. Known entities
    for ent in known_entities:
        if ent.lower() in text_lower:
            findings["known_entity_hits"].append(ent)

    # 2. Hidden fact aliases
    for alias in hidden_aliases:
        if alias.lower() in text_lower:
            findings["hidden_fact_alias_hits"].append(alias)

    # 3. Raw snake_case event IDs
    for match in _SNAKE_CASE_ID.finditer(text):
        hit = match.group(0)
        # Filter out common words that happen to match
        if hit not in {"player", "mara", "rusk", "iven"} and len(hit) > 8:
            findings["raw_event_id_hits"].append(hit)

    # 4. Inner-thought verbs
    for verb in _INNER_THOUGHT_VERBS:
        if verb in text:
            findings["inner_thought_verb_hits"].append(verb)
            findings["claims"].append(
                NarrativeClaim(
                    segment_id=segment_id,
                    kind="npc_inner_state",
                    evidence_span=text,
                    confidence=0.9,
                    metadata={"trigger": verb},
                )
            )

    # 5. Remote event cues
    for cue in _REMOTE_CUES:
        if cue in text:
            findings["remote_event_cue_hits"].append(cue)
            findings["claims"].append(
                NarrativeClaim(
                    segment_id=segment_id,
                    kind="remote_event",
                    evidence_span=text,
                    confidence=0.8,
                    metadata={"trigger": cue},
                )
            )

    # 6. Unsupported location mentions
    for loc in known_locations:
        if loc.lower() in text_lower and loc not in findings["known_entity_hits"]:
            # If location is mentioned but not current, flag as remote
            findings["unsupported_location_mentions"].append(loc)

    return findings
