"""Hook generator — v0.3.1.

Generates EventHooks from TurnRecord, canon_delta, and validation failures.
Deterministic rules for movement, conversation, blocked entry, force attempts.
"""
from __future__ import annotations

from .hooks import merge_similar_hooks
from .models import Claim, ClaimStatus, EventHook, Fact, Knowledge, ProposedEffect, WorldState


# ---------- public API ----------


def generate_hooks(world: WorldState, turn_record) -> list[str]:
    """Generate new hooks from a completed turn. Returns created hook ids."""
    new_hooks: list[EventHook] = []
    text = turn_record.action_text
    delta = turn_record.canon_delta
    turn = turn_record.turn
    loc = _player_location(world)

    # 1. Movement to new location
    facts_added = delta.get("facts_added", [])
    for f in facts_added:
        if f.predicate == "at" and f.args[0] == "player":
            new_place = f.args[1]
            new_hooks.append(_make_return_hook(world, new_place, turn))
            npcs = _npcs_at(world, new_place)
            for npc in npcs:
                new_hooks.append(_make_meet_npc_hook(world, npc, new_place, turn))

    # 2. Blocked access (rejected movement)
    if not turn_record.validation.ok:
        reason = turn_record.validation.reason
        if any(k in reason for k in ("inaccessible", "sealed", "blocked")):
            place = _extract_place_from_reason(reason) or loc
            if place:
                new_hooks.append(_make_blocked_access_hook(world, place, text, turn))

    # 3. Social interaction with NPCs
    if turn_record.hypothesis_kind in ("ask_about_topic", "confront_about_topic", "complain_about_service", "order_drink"):
        targets = turn_record.touched - {"player"} if turn_record.touched else set()
        for t in targets:
            if t in world.npcs:
                new_hooks.append(_make_npc_interaction_hook(world, t, text, turn_record))

    # 4. Failed force/break attempts
    if any(c in text for c in ("掰开", "强行", "force", "砸", "break", "撬")):
        new_hooks.append(_make_force_attempt_hook(world, loc, text, turn))

    # 5. Evasive/cold NPC response
    observations = delta.get("observations", [])
    for obs in observations:
        obs_str = str(obs).lower()
        if any(k in obs_str for k in ("evasive", "cold", "defensive", "avoid", "闪烁")):
            targets = turn_record.touched - {"player"} if turn_record.touched else set()
            for t in targets:
                if t in world.npcs:
                    new_hooks.append(_make_evasive_npc_hook(world, t, text, turn))

    # Register hooks with unique ids
    created_ids: list[str] = []
    for hook in new_hooks:
        hid = _unique_hook_id(world, hook.hook_type)
        hook.id = hid
        world.hooks[hid] = hook
        created_ids.append(hid)

    # Merge similar communicate hooks
    merge_similar_hooks(world)

    return created_ids


# ---------- hook builders ----------


def _make_return_hook(world: WorldState, place: str, turn: int) -> EventHook:
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[f"player_visited_{place}"],
        hook_type="return",
        trigger_cues=["回去", "返回", "再去", "回到", "return", "go back", place],
        valid_targets=[],
        topics=[place],
        places=[place],
        priority=0.4,
        ttl=5,
        decay_policy="decay_each_turn",
    )


def _make_meet_npc_hook(world: WorldState, npc: str, place: str, turn: int) -> EventHook:
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[f"player_met_{npc}_at_{place}"],
        hook_type="communicate",
        trigger_cues=["告诉", "说起", "提起", npc, place, "见到"],
        valid_targets=_other_npcs(world, npc),
        topics=[npc, place],
        places=[place],
        participants=[npc],
        priority=0.5,
        ttl=4,
        decay_policy="consume_once",
    )


def _make_blocked_access_hook(world: WorldState, place: str, text: str, turn: int) -> EventHook:
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[f"old_mine_access_blocked", f"player_attempted_{place}"],
        hook_type="communicate",
        trigger_cues=["刚才", "情形", "告诉", "提起", "大门", " blocked", "sealed", "封印", place],
        valid_targets=["mara"],
        payload_claims=[
            Claim("player_knows", (f"{place}_access_blocked",), ClaimStatus.ACCEPTED, "玩家亲历"),
        ],
        proposed_effects=[
            ProposedEffect("add_knowledge", (Knowledge("mara", Fact("sealed", (place,))),), 2),
            ProposedEffect("belief_delta", ("rusk_pressures_mara", 0.04), 2),
            ProposedEffect("observe", ("mara_tenses_at_rusk",), 0),
        ],
        topics=[place, "seal", "access"],
        places=[place],
        priority=0.75,
        ttl=5,
        decay_policy="consume_once",
    )


def _make_npc_interaction_hook(world: WorldState, npc: str, text: str, turn_record) -> EventHook:
    turn = turn_record.turn
    topic = turn_record.touched - {"player", npc} if turn_record.touched else set()
    topics = list(topic) if topic else ["conversation"]

    # Determine tone from observations
    observations = turn_record.canon_delta.get("observations", [])
    tone = "neutral"
    for obs in observations:
        obs_str = str(obs).lower()
        if any(k in obs_str for k in ("evasive", "cold", "defensive", "avoid")):
            tone = "evasive"
        elif any(k in obs_str for k in ("warm", "friendly", "helpful")):
            tone = "friendly"

    event_key = f"{npc}_was_{tone}_to_player"
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[event_key, f"player_spoke_with_{npc}"],
        hook_type="communicate",
        trigger_cues=["告诉", "说起", "提起", npc, "刚才", "情形"] + topics,
        valid_targets=_other_npcs(world, npc),
        payload_claims=[
            Claim("player_knows", (event_key,), ClaimStatus.ACCEPTED, "玩家亲历"),
        ],
        proposed_effects=[
            ProposedEffect("add_knowledge", (Knowledge("mara", Fact("observed", (npc, tone))),), 2),
            ProposedEffect("belief_delta", (f"{npc}_attitude_toward_player", 0.03), 2),
        ],
        topics=topics + [npc],
        participants=[npc],
        priority=0.6 if tone == "evasive" else 0.5,
        ttl=4 if tone == "evasive" else 3,
        decay_policy="consume_once",
    )


def _make_force_attempt_hook(world: WorldState, place: str, text: str, turn: int) -> EventHook:
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[f"player_attempted_force_{place}", "force_gate_failed"],
        hook_type="communicate",
        trigger_cues=["刚才", "情形", "告诉", "强行", "掰开", "失败", "gate", "force", place],
        valid_targets=["mara"],
        payload_claims=[
            Claim("player_knows", ("force_gate_attempt_failed",), ClaimStatus.ACCEPTED, "玩家亲历"),
        ],
        proposed_effects=[
            ProposedEffect("add_knowledge", (Knowledge("mara", Fact("player_attempted_force_gate", ())),), 2),
            ProposedEffect("belief_delta", ("rusk_pressures_mara", 0.05), 2),
            ProposedEffect("observe", ("mara_shocked_at_force_attempt",), 0),
        ],
        topics=[place, "force", "gate"],
        places=[place],
        priority=0.7,
        ttl=5,
        decay_policy="consume_once",
    )


def _make_evasive_npc_hook(world: WorldState, npc: str, text: str, turn: int) -> EventHook:
    return EventHook(
        id="",
        owner="player",
        source_turn=turn,
        source_events=[f"{npc}_was_evasive_or_cold"],
        hook_type="confront",
        trigger_cues=["质问", "为什么", "刚才", npc, "回避", "闪烁"],
        valid_targets=[npc],
        payload_claims=[
            Claim("player_knows", (f"{npc}_was_evasive_or_cold",), ClaimStatus.ACCEPTED, "玩家亲历"),
        ],
        proposed_effects=[
            ProposedEffect("rel_delta", (npc, "player", "trust", -0.05), 1),
            ProposedEffect("observe", (f"{npc}_defensive_about_confrontation",), 0),
        ],
        topics=[npc, "evasion"],
        participants=[npc],
        priority=0.65,
        ttl=6,
        decay_policy="consume_once",
    )


# ---------- utilities ----------


def _player_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _npcs_at(world: WorldState, loc: str) -> list[str]:
    out: list[str] = []
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if entity != "player" and place == loc and entity in world.npcs:
                out.append(entity)
    return out


def _other_npcs(world: WorldState, exclude: str) -> list[str]:
    """Return NPCs other than the excluded one."""
    return [n for n in world.npcs if n != exclude]


def _extract_place_from_reason(reason: str) -> str:
    """Try to extract a place name from a validation failure reason."""
    # e.g. "location_inaccessible(old_mine)" -> "old_mine"
    if "(" in reason and ")" in reason:
        start = reason.index("(") + 1
        end = reason.index(")")
        return reason[start:end].split(",")[0]
    return ""


_hook_counter: dict[str, int] = {}


def _unique_hook_id(world: WorldState, hook_type: str) -> str:
    """Generate a unique hook id."""
    prefix = f"H_{hook_type}"
    existing = [h for h in world.hooks if h.startswith(prefix)]
    idx = len(existing) + 1
    return f"{prefix}_{idx}"
