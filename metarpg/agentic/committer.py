"""Committer — the only layer that applies admitted patch effects to WorldState.

Converts admitted effects into existing WorldState operations.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.schemas import CandidatePatchEffect, Commitment, Operation, Segment, TurnTransaction
from metarpg.models import EntityState, Fact, Knowledge, WorldState


def apply_admitted_patch(
    world: WorldState,
    admitted_patch: list[CandidatePatchEffect],
    final_segments: list[Segment],
) -> dict[str, Any]:
    """Apply admitted patch effects to world state. Returns delta summary."""
    delta: dict[str, Any] = {
        "facts_added": [],
        "facts_removed": [],
        "knowledge_added": [],
        "relations_changed": [],
        "beliefs_changed": [],
        "items_consumed": [],
        "items_acquired": [],
        "hooks_created": [],
        "journal_notes": [],
        "events": [],
    }

    for eff in admitted_patch:
        kind = eff.kind
        args = eff.args

        if kind == "add_fact":
            pred = args.get("predicate", "")
            fargs = tuple(args.get("args", []))
            if pred and fargs:
                f = Fact(pred, fargs)
                world.facts.add(f)
                delta["facts_added"].append(str(f))

        elif kind == "remove_fact":
            pred = args.get("predicate", "")
            fargs = tuple(args.get("args", []))
            if pred and fargs:
                f = Fact(pred, fargs)
                world.facts.discard(f)
                delta["facts_removed"].append(str(f))

        elif kind == "move":
            entity = args.get("entity", "player")
            dest = args.get("destination", "")
            if dest:
                # Remove old location fact
                old = [f for f in world.facts if f.predicate == "at" and f.args[0] == entity]
                for o in old:
                    world.facts.discard(o)
                    delta["facts_removed"].append(str(o))
                # Add new location fact
                f = Fact("at", (entity, dest))
                world.facts.add(f)
                delta["facts_added"].append(str(f))
                # Auto-register new location
                world.locations.add(dest)

        elif kind == "consume_item":
            item = args.get("item", "")
            if item:
                f = Fact("has", ("player", item))
                world.facts.discard(f)
                delta["items_consumed"].append(item)

        elif kind == "acquire_item":
            item = args.get("item", "")
            if item:
                f = Fact("has", ("player", item))
                world.facts.add(f)
                delta["items_acquired"].append(item)

        elif kind == "knowledge_transfer":
            agent = args.get("agent", "")
            pred = args.get("predicate", "")
            fargs = tuple(args.get("args", []))
            if agent and pred:
                k = Knowledge(agent, Fact(pred, fargs))
                world.knowledge.add(k)
                delta["knowledge_added"].append(str(k))

        elif kind == "relation_delta":
            a = args.get("from", "")
            b = args.get("to", "")
            dim = args.get("dim", "")
            val = args.get("delta", 0.0)
            if a and b and dim:
                rel = world.ensure_relation(a, b)
                rel.update(dim, val)
                delta["relations_changed"].append(f"{a}->{b} {dim}={val:+.2f}")

        elif kind == "belief_delta":
            bid = args.get("belief_id", "")
            val = args.get("delta", 0.0)
            if bid in world.beliefs:
                world.beliefs[bid].prob += val
                world.beliefs[bid].clip()
                delta["beliefs_changed"].append(f"{bid} p={world.beliefs[bid].prob:.2f}")

        elif kind == "journal_note":
            note = args.get("text", "")
            if note:
                delta["journal_notes"].append(note)
                world.journal_notes.append(note)
                world.turn_event_log.append(f"journal:{note}")

        elif kind == "transient_event":
            name = args.get("name", "")
            desc = args.get("description", "")
            event_str = name or desc
            if event_str:
                delta["events"].append(event_str)
                world.turn_event_log.append(event_str)

        elif kind == "observe_reaction":
            target = args.get("target", "")
            reaction = args.get("reaction", "")
            if target:
                event_str = f"observe:{target}:{reaction}"
                delta["events"].append(event_str)
                world.turn_event_log.append(event_str)

        elif kind == "create_hook":
            hid = args.get("hook_id", "")
            if hid:
                delta["hooks_created"].append(hid)

    # Build player output from final segments
    player_output = "\n".join(s.text for s in final_segments)

    return {
        "delta": delta,
        "player_output": player_output,
        "turn": world.turn,
    }


def commit_turn(
    world: WorldState,
    admitted_patch: list[CandidatePatchEffect],
    final_segments: list[Segment],
) -> dict[str, Any]:
    """Full commit: apply patch, increment turn, auto-init new entities."""
    world.turn += 1
    result = apply_admitted_patch(world, admitted_patch, final_segments)
    result["turn"] = world.turn
    # v0.6.6: ensure all known NPCs have an EntityState
    for npc in world.npcs:
        if npc not in world.entity_states:
            world.entity_states[npc] = EntityState(name=npc)
    # Also scan segment text for any named entity that slipped in
    _auto_init_new_entities(world, final_segments)
    return result


# ---------------------------------------------------------------------------
# v0.7.0 — Transaction commit path (new interface, legacy commit_turn untouched)
# ---------------------------------------------------------------------------


def commit_transaction(world: WorldState, tx: "TurnTransaction") -> dict[str, Any]:
    """Apply a validated TurnTransaction to WorldState.

    Does NOT increment turn here; caller or legacy path handles it.
    For standalone v0.7.0 pipeline, turn increment is done at end.
    """
    _ensure_v070_fields(world)

    delta: dict[str, Any] = {
        "facts_added": [],
        "facts_removed": [],
        "events": [],
        "utterances": [],
        "relations_changed": [],
        "beliefs_changed": [],
        "hooks_changed": [],
        "affordances_added": [],
    }

    for op in tx.operations:
        _apply_operation(world, op, delta)

    for c in tx.commitments:
        _apply_commitment(world, c, delta)

    world.turn += 1
    if "turn" in world.world_time:
        world.world_time["turn"] = world.turn

    return {"delta": delta, "turn": world.turn}


def _ensure_v070_fields(world: WorldState) -> None:
    if not hasattr(world, "events"):
        world.events = []
    if not hasattr(world, "utterances"):
        world.utterances = []
    if not hasattr(world, "hints"):
        world.hints = {}
    if not hasattr(world, "affordances"):
        world.affordances = {}
    if not hasattr(world, "_hook_status"):
        world._hook_status = {}


def _apply_operation(
    world: WorldState, op: "Operation", delta: dict[str, Any]
) -> None:
    kind = op.kind
    params = op.params

    if kind == "move_player":
        dest = params.get("destination")
        entity = params.get("entity", "player")
        if not dest:
            return
        old = [f for f in world.facts if f.predicate == "at" and f.args[0] == entity]
        for o in old:
            world.facts.discard(o)
            delta["facts_removed"].append(str(o))
        f = Fact("at", (entity, dest))
        world.facts.add(f)
        delta["facts_added"].append(str(f))
        world.locations.add(dest)

    elif kind == "speak":
        world.utterances.append(
            {
                "entity": params.get("entity"),
                "text": params.get("text"),
                "turn": world.turn,
            }
        )
        delta["utterances"].append(params.get("text", ""))

    elif kind == "transfer_item":
        item = params.get("item")
        if not item:
            return
        from_entity = params.get("from_entity")
        to_entity = params.get("to_entity")
        if from_entity:
            old_f = Fact("has", (from_entity, item))
            world.facts.discard(old_f)
            delta["facts_removed"].append(str(old_f))
        if to_entity:
            new_f = Fact("has", (to_entity, item))
            world.facts.add(new_f)
            delta["facts_added"].append(str(new_f))

    elif kind == "update_relation":
        a = params.get("entity_a")
        b = params.get("entity_b")
        dim = params.get("dim")
        val = params.get("delta", 0.0)
        if a and b and dim:
            rel = world.ensure_relation(a, b)
            rel.update(dim, val)
            delta["relations_changed"].append(f"{a}->{b} {dim}={val:+.2f}")

    elif kind == "update_belief":
        bid = params.get("belief_id")
        val = params.get("delta", 0.0)
        if bid in world.beliefs:
            world.beliefs[bid].prob += val
            world.beliefs[bid].clip()
            delta["beliefs_changed"].append(
                f"{bid} p={world.beliefs[bid].prob:.2f}"
            )

    elif kind == "mark_hook_status":
        hid = params.get("hook_id")
        status = params.get("status")
        if hid:
            world._hook_status[hid] = status
            delta["hooks_changed"].append(f"{hid} -> {status}")

    elif kind == "add_event":
        world.events.append(
            {
                "type": params.get("event_type", "generic"),
                "summary": params.get("summary", ""),
                "turn": world.turn,
            }
        )
        delta["events"].append(params.get("summary", ""))

    elif kind in ("inner_monologue", "add_texture"):
        pass  # no world state change


def _apply_commitment(
    world: WorldState, c: "Commitment", delta: dict[str, Any]
) -> None:
    if c.level == "event":
        world.events.append({"description": c.description, "turn": world.turn})
        delta["events"].append(c.description)

    elif c.level == "utterance":
        world.utterances.append({"description": c.description, "turn": world.turn})
        delta["utterances"].append(c.description)

    elif c.level == "affordance":
        aid = c.metadata.get(
            "affordance_id", f"aff_{world.turn}_{len(world.affordances)}"
        )
        world.affordances[aid] = {"description": c.description, "turn": world.turn}
        delta["affordances_added"].append(aid)

    elif c.level in ("texture", "hint", "belief_evidence", "inner_monologue"):
        pass  # no direct world state change in MVP


def _auto_init_new_entities(world: WorldState, segments: list[Segment]) -> None:
    """Create EntityState for any named entity not yet tracked."""
    for seg in segments:
        text = seg.text
        # Known NPCs
        for npc in world.npcs:
            if npc in text and npc not in world.entity_states:
                world.entity_states[npc] = EntityState(name=npc)
        # Known locations (some may be named entities too)
        for loc in world.locations:
            if loc in text and loc not in world.entity_states:
                world.entity_states[loc] = EntityState(name=loc)
