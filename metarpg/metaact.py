"""MetaAct builder — extract local context + surface cues from raw player text.

A MetaAct is raw player behavior wrapped with local world context. It is not
yet a game action. The proposer layer interprets it into hypotheses.
"""
from __future__ import annotations

import re
from typing import Iterable

from .models import Belief, Fact, MetaAct, WorldState


# Chinese punctuation to strip/split on
_PUNCT = "，。！？；：、\"\"''（）【】"

# Known entity/location keywords for cue extraction (merged with scenario data)
_KNOWN_ENTITY_CUES = {"玛拉", "拉斯克", "艾文", "伊文", "player"}
_KNOWN_LOCATION_CUES = {"酒馆", "守卫站", "老矿", "矿场", "矿口", "地窖"}
_KNOWN_TOPIC_CUES = {"矿", "矿场", "老矿", "艾文", "伊文", "酒", "啤酒", "麦芽"}


def build_metaact(text: str, world: WorldState) -> MetaAct:
    """Build a MetaAct from raw text + current world state."""
    loc = _player_location(world)
    nearby = _nearby_npcs(world, loc)
    local_facts = _relevant_facts(world, nearby + ["player", loc])
    local_beliefs = _relevant_beliefs(world, nearby)
    speech = _extract_speech(text)
    cues = _extract_surface_cues(text, nearby, world)

    return MetaAct(
        raw_text=text,
        actor="player",
        turn=world.turn,
        local_entities=nearby,
        local_facts=local_facts,
        local_beliefs=local_beliefs,
        speech_fragments=speech,
        surface_cues=cues,
        player_location=loc,
    )


# ---------- helpers ----------


def _player_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _nearby_npcs(world: WorldState, loc: str) -> list[str]:
    out: list[str] = []
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if entity != "player" and place == loc and entity in world.npcs:
                out.append(entity)
    return out


def _relevant_facts(world: WorldState, touched: Iterable[str]) -> list[Fact]:
    """Pull facts that mention any touched entity or location."""
    out: list[Fact] = []
    for f in world.facts:
        if any(a in touched for a in f.args):
            out.append(f)
    return out


def _relevant_beliefs(world: WorldState, nearby: list[str]) -> list[Belief]:
    """Pull beliefs that mention nearby entities or player location."""
    loc = _player_location(world)
    touched = set(nearby) | {loc, "player"}
    out: list[Belief] = []
    for b in world.beliefs.values():
        if any(t in b.description for t in touched):
            out.append(b)
    return out


# Quoted speech extraction — supports "..." and "..."
_SPEECH_RE = re.compile(r'[""""]([^""""]+)[""""]')


def _extract_speech(text: str) -> list[str]:
    return _SPEECH_RE.findall(text)


def _extract_surface_cues(text: str, nearby: list[str], world: WorldState) -> list[str]:
    """Extract meaningful words/phrases from raw text.

    Strategy:
    1. Strip punctuation, split into tokens.
    2. Keep tokens that match known entity/location/topic cues.
    3. Keep tokens that match scenario-specific cues from world state.
    """
    cleaned = text
    for ch in _PUNCT:
        cleaned = cleaned.replace(ch, " ")
    cleaned = cleaned.replace("　", " ")
    tokens = [t.strip() for t in cleaned.split() if t.strip()]

    cues: list[str] = []
    known = _KNOWN_ENTITY_CUES | _KNOWN_LOCATION_CUES | _KNOWN_TOPIC_CUES
    # Add NPC names from world state
    known |= world.npcs
    # Add location names from world state
    known |= world.locations

    for tok in tokens:
        if tok in known:
            cues.append(tok)
        # Also check if token contains any known cue as substring
        for cue in known:
            if cue in tok and cue not in cues:
                cues.append(cue)

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in cues:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
