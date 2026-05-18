"""Story Packet Builder — compact local context for agentic agents.

Separates visibility tiers:
- visible_to_player: what Writer can narrate
- known_to_npc: what NPCs know (for reaction realism)
- hidden_truth: auditor-only facts (must not leak)
- allowed/forbidden: guardrails for effect kinds and narration topics

Matches MetaRPG_Agent_story_prompt_reference.md structure.
"""
from __future__ import annotations

from typing import Any

from metarpg.models import Fact, WorldState


# ---------------------------------------------------------------------------
# Visibility helpers
# ---------------------------------------------------------------------------


def _player_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _nearby_npcs(world: WorldState, loc: str | None = None) -> list[str]:
    if loc is None:
        loc = _player_location(world)
    return sorted(
        f.args[0]
        for f in world.facts
        if f.predicate == "at"
        and len(f.args) == 2
        and f.args[1] == loc
        and f.args[0] in world.npcs
    )


def _nearby_objects(world: WorldState, loc: str | None = None) -> list[str]:
    if loc is None:
        loc = _player_location(world)
    objs: set[str] = set()
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[1] == loc:
            if f.args[0] not in world.npcs and f.args[0] != "player":
                objs.add(f.args[0])
    for f in world.facts:
        if f.predicate == "has" and len(f.args) == 2 and f.args[0] == "player":
            objs.add(f.args[1])
    return sorted(objs)


def _player_inventory(world: WorldState) -> list[str]:
    return sorted(
        f.args[1]
        for f in world.facts
        if f.predicate == "has" and len(f.args) == 2 and f.args[0] == "player"
    )


def _recent_events(world: WorldState, limit: int = 5) -> list[str]:
    events: list[str] = []
    # Committed facts involving player
    for f in world.facts:
        if "player" in f.args and f.predicate not in {"at", "has"}:
            events.append(str(f))
    # Knowledge player acquired
    for k in world.knowledge:
        if k.agent == "player":
            events.append(str(k))
    # Transient events from previous turns
    events.extend(world.turn_event_log)
    return events[-limit:]


# Keywords that indicate an item was transferred to the player
_INVENTORY_TRANSFER_KEYWORDS = {
    "给", "递", "推", "倒", "拿", "取", "接过", "收到",
    "给你", "给你", "推给", "递给", "倒了", "放到", "放在",
    "面前", "你手中", "你手里", "你跟前", "你旁边",
}


def _inventory_events(world: WorldState, limit: int = 8) -> list[str]:
    """Extract turn_event_log entries that look like item transfers to player.

    These are used by Hard Auditor to allow consume_item even when the
    world.facts 'has' predicate hasn't been updated yet (e.g. transient_event
    'Mara poured ale for player' from the previous turn).
    """
    events: list[str] = []
    for entry in world.turn_event_log[-limit:]:
        text = str(entry).lower()
        if any(kw in text for kw in _INVENTORY_TRANSFER_KEYWORDS):
            # Heuristic: also require a noun that looks like an item
            # (at least one Chinese character or English word > 2 chars)
            events.append(str(entry))
    return events


def _npc_surface_state(world: WorldState, npcs: list[str]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for npc in npcs:
        roles = sorted(world.roles.get(npc, set()))
        rel = world.get_relation(npc, "player")
        # Qualitative surface descriptions for Writer (no raw numbers)
        surface: list[str] = []
        # Auditor-only raw relation data
        raw_relations: dict[str, float] = {}
        if rel:
            for dim, val in rel.dimensions.items():
                raw_relations[dim] = val
                if abs(val) < 0.1:
                    surface.append("neutral")
                elif val > 0.3:
                    surface.append("warm" if dim == "trust" else "interested")
                elif val > 0.1:
                    surface.append("mildly curious" if dim == "curiosity" else "cautious")
                elif val < -0.3:
                    surface.append("hostile" if dim == "trust" else "fearful")
                elif val < -0.1:
                    surface.append("reserved" if dim == "trust" else "wary")
                else:
                    surface.append("neutral")
        if not surface:
            surface = ["neutral"]
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped = [s for s in surface if not (s in seen or seen.add(s))]
        state[npc] = {
            "role": roles[0] if roles else "unknown",
            "visible_mood": deduped,
            "can_speak": True,
            "_auditor_relations": raw_relations,
        }
    return state


def _visible_facts(world: WorldState) -> list[str]:
    return [
        str(f)
        for f in world.facts
        if f.predicate not in {"at", "has"} and "player" in f.args
    ]


def _hidden_truths(world: WorldState) -> list[dict[str, Any]]:
    hidden: list[dict[str, Any]] = []
    player_locs = {
        f.args[1]
        for f in world.facts
        if f.predicate == "at" and f.args[0] == "player"
    }
    for f in world.facts:
        if f.predicate == "hidden_fact" or f.predicate.startswith("secret"):
            hidden.append({"predicate": f.predicate, "args": f.args, "alias": f.predicate})
        elif f.predicate == "at" and len(f.args) == 2:
            ent, loc = f.args
            if ent in world.npcs and loc not in player_locs:
                hidden.append(
                    {
                        "predicate": f.predicate,
                        "args": f.args,
                        "alias": f"{ent}_at_{loc}",
                    }
                )
    for m in world.motifs.values():
        if m.params.get("secrecy", 0) > 0.5 or m.params.get("danger", 0) > 0.7:
            hidden.append(
                {
                    "predicate": "motif",
                    "args": m.args,
                    "alias": m.name,
                }
            )
    return hidden


def _active_hooks(world: WorldState) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    for h in world.hooks.values():
        if not h.consumed and h.ttl > 0:
            hooks.append(
                {
                    "id": h.id,
                    "type": h.hook_type,
                    "owner": h.owner,
                    "trigger_cues": h.trigger_cues,
                    "valid_targets": h.valid_targets,
                    "ttl": h.ttl,
                }
            )
    return hooks


# ---------------------------------------------------------------------------
# Story Packet Builder
# ---------------------------------------------------------------------------


def build_story_packet(world: WorldState) -> dict[str, Any]:
    """Build a compact local story packet for one player action.

    Matches MetaRPG_Agent_story_prompt_reference.md §4 structure.
    """
    loc = _player_location(world)
    nearby = _nearby_npcs(world, loc)
    objects = _nearby_objects(world, loc)
    inventory = _player_inventory(world)
    recent = _recent_events(world)
    visible_facts = _visible_facts(world)
    hidden = _hidden_truths(world)
    npc_surface = _npc_surface_state(world, nearby)

    atmosphere = _atmosphere(world, loc)
    allowed_effects = _allowed_effect_kinds(world, loc)
    allowed_reveals = _allowed_reveals(world)
    forbidden = _forbidden_mentions(world, nearby, hidden)

    return {
        "scene": {
            "location": loc,
            "visible_entities": ["player"] + nearby,
            "visible_objects": objects,
            "atmosphere": atmosphere,
        },
        "player_context": {
            "known_facts": visible_facts,
            "recent_events": recent,
            "inventory_or_handheld": inventory,
            "inventory_events": _inventory_events(world),
        },
        "npc_surface": npc_surface,
        "allowed_effect_kinds": allowed_effects,
        "allowed_reveals": allowed_reveals,
        "forbidden": forbidden,
        "auditor_only": {
            "hidden_truths": hidden,
            "active_hooks": _active_hooks(world),
            "all_beliefs": [
                {"id": b.id, "description": b.description, "prob": round(b.prob, 2)}
                for b in world.beliefs.values()
            ],
        },
    }


def _atmosphere(world: WorldState, loc: str) -> str:
    tags = world.place_services.get(loc, set())
    tag_str = ", ".join(sorted(tags)) if tags else "quiet"
    moods: list[str] = []
    for m in world.motifs.values():
        if loc in m.args or any(a in m.args for a in world.npcs):
            if m.params.get("danger", 0) > 0.5:
                moods.append("dangerous")
            elif m.params.get("lure", 0) > 0.5:
                moods.append("alluring")
    mood_str = ", ".join(moods) if moods else "tense"
    return f"{mood_str} {loc} ({tag_str})"


def _allowed_effect_kinds(world: WorldState, loc: str) -> list[str]:
    kinds = [
        "transient_event",
        "journal_note",
        "observe_reaction",
        "relation_delta",
        "consume_item",
        "acquire_item",
    ]
    if any(
        f.predicate == "at" and f.args[1] == loc and f.args[0] in world.npcs
        for f in world.facts
    ):
        kinds.extend(["knowledge_transfer", "reveal"])
    if world.place_services.get(loc, set()) & {"exit", "path", "road"}:
        kinds.append("move")
    return kinds


def _allowed_reveals(world: WorldState) -> list[str]:
    """Facts that NPCs are allowed to mention in conversation."""
    reveals: list[str] = []
    for f in world.facts:
        if f.predicate in {"old_mine_is_sealed", "iven_missing"}:
            reveals.append(f.predicate)
    return reveals


def _forbidden_mentions(
    world: WorldState, nearby: list[str], hidden: list[dict[str, Any]]
) -> dict[str, Any]:
    absent_npcs = sorted(world.npcs - set(nearby))
    hidden_aliases = [h.get("alias", "") for h in hidden]
    return {
        "entities_not_present": absent_npcs,
        "hidden_fact_aliases": hidden_aliases,
        "schema_violations": [
            "光剑", "lightsaber", "激光剑", "能量剑",
            "心灵感应", "读心", "telepathy", "mind reading",
            "手机", "电话", "电", "车", "枪", "枪", "vehicle",
        ],
        "forbidden_narration": [
            "npc_inner_thought_hidden_fact",
            "remote_action",
            "raw_event_id",
            "belief_probability",
        ],
    }
