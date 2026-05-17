"""Authoritative event applier — v0.4.

Only apply_event mutates WorldState. All state changes route through here.

Current world.apply_patch is preserved as a thin wrapper that delegates to
apply_events internally. This file is the canonical location for state-mutation
logic.

Rules:
  - apply_event never invents facts.
  - It only mutates what the event payload explicitly requests.
  - It returns (outcome, reason, delta) so callers know what happened.
  - For deferred outcomes, no state is mutated.
"""
from __future__ import annotations

from typing import Any

from .events import AdmittedEvent, EventApplyOutcome
from .models import Belief, Fact, Knowledge, Motif, WorldState


# ---------- public API ----------


def apply_event(world: WorldState, event: AdmittedEvent) -> tuple[EventApplyOutcome, str, dict[str, Any]]:
    """Apply a single admitted event to world state.

    Returns (outcome, reason, delta).
    Delta is a dict of mutation records (e.g. {"facts_added": [Fact(...)]}).
    """
    k = event.kind
    p = event.payload

    # Narrative-only events (no state mutation, but recorded in delta)
    if k == "transient_event":
        return EventApplyOutcome.APPLIED, "", {"transient_events": [p[0]]}

    if k in ("event", "canon_event"):
        return EventApplyOutcome.APPLIED, "", {"events": [p[0]]}

    if k == "observe":
        return EventApplyOutcome.APPLIED, "", {"observations": [p[0]]}

    if k == "dialogue":
        return EventApplyOutcome.APPLIED, "", {"dialogues": [p[0]]}

    # State mutations
    if k == "travel":
        return _apply_travel(world, p)

    if k == "add_fact":
        return _apply_add_fact(world, p)

    if k == "remove_fact":
        return _apply_remove_fact(world, p)

    if k == "add_knowledge":
        return _apply_add_knowledge(world, p)

    if k == "add_object":
        return _apply_add_object(world, p)

    if k == "remove_object":
        return _apply_remove_object(world, p)

    if k == "relationship_change":
        return _apply_relationship_change(world, p)

    if k == "rel_delta":
        return _apply_rel_delta(world, p)

    if k == "belief_delta":
        return _apply_belief_delta(world, p)

    if k == "motif_delta":
        return _apply_motif_delta(world, p)

    if k == "attention_delta":
        return _apply_attention_delta(world, p)

    if k == "risk_flag":
        return EventApplyOutcome.APPLIED, "", {"risk_flags": [p[0]]}

    if k == "flag_set":
        return EventApplyOutcome.APPLIED, "", {"flags_set": [(p[0], p[1])]}

    # Hook lifecycle events
    if k == "hook_create":
        return _apply_hook_create(world, p)

    if k == "consume_hook":
        return _apply_hook_consume(world, p)

    if k == "decay_hook":
        return _apply_hook_decay(world, p)

    if k == "promote_hook":
        return _apply_promote_hook(world, p)

    # Graph/planning events (narrative bookkeeping only in v0.4)
    if k in ("motif_activate", "motif_resolve", "plot_thread_open", "plot_thread_advance", "plot_thread_close"):
        return EventApplyOutcome.APPLIED, "", {"graph_events": [(k, p)]}

    # Unknown event kind — rejected with clear reason
    return EventApplyOutcome.REJECTED, f"unknown_event_kind({k})", {}


def apply_events(world: WorldState, events: list[AdmittedEvent]) -> "ApplyReport":
    """Apply multiple events, collecting outcomes into an ApplyReport."""
    from .apply_report import ApplyReport

    report = ApplyReport()
    for ev in events:
        outcome, reason, delta = apply_event(world, ev)
        report.record(ev, outcome, reason, delta)
    return report


# ---------- state mutation handlers ----------


def _apply_travel(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    """travel(agent, from_place, to_place) or travel(agent, to_place)."""
    if len(p) >= 3:
        agent, from_place, to_place = p[0], p[1], p[2]
    else:
        agent, to_place = p[0], p[1]
        from_place = _location_of(world, agent)

    delta: dict[str, list] = {}
    if from_place:
        old = Fact("at", (agent, from_place))
        if old in world.facts:
            world.facts.discard(old)
            delta.setdefault("facts_removed", []).append(old)
    new = Fact("at", (agent, to_place))
    if new not in world.facts:
        world.facts.add(new)
        delta.setdefault("facts_added", []).append(new)
    return EventApplyOutcome.APPLIED, "", delta


def _apply_add_fact(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    fact: Fact = p[0]
    if fact not in world.facts:
        world.facts.add(fact)
        return EventApplyOutcome.APPLIED, "", {"facts_added": [fact]}
    return EventApplyOutcome.APPLIED, "", {}  # idempotent


def _apply_remove_fact(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    fact: Fact = p[0]
    if fact in world.facts:
        world.facts.discard(fact)
        return EventApplyOutcome.APPLIED, "", {"facts_removed": [fact]}
    return EventApplyOutcome.APPLIED, "", {}


def _apply_add_knowledge(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    kn: Knowledge = p[0]
    if kn not in world.knowledge:
        world.knowledge.add(kn)
        return EventApplyOutcome.APPLIED, "", {"knowledge_added": [kn]}
    return EventApplyOutcome.APPLIED, "", {}


def _apply_add_object(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    obj, place = p[0], p[1]
    fact = Fact("at", (obj, place))
    delta: dict[str, list] = {}
    if fact not in world.facts:
        world.facts.add(fact)
        delta.setdefault("facts_added", []).append(fact)
    delta.setdefault("objects_added", []).append((obj, place))
    return EventApplyOutcome.APPLIED, "", delta


def _apply_remove_object(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    obj, place = p[0], p[1]
    fact = Fact("at", (obj, place))
    delta: dict[str, list] = {}
    if fact in world.facts:
        world.facts.discard(fact)
        delta.setdefault("facts_removed", []).append(fact)
    delta.setdefault("objects_removed", []).append((obj, place))
    return EventApplyOutcome.APPLIED, "", delta


def _apply_relationship_change(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    """relationship_change(from_agent, to_agent, dim, delta_val)."""
    from_a, to_a, dim, dval = p[0], p[1], p[2], float(p[3])
    rel = world.ensure_relation(from_a, to_a)
    rel.update(dim, dval)
    return EventApplyOutcome.APPLIED, "", {"rel_deltas": [(from_a, to_a, dim, dval)]}


def _apply_rel_delta(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    """rel_delta(from_agent, to_agent, dim, delta_val) — alias for relationship_change."""
    return _apply_relationship_change(world, p)


def _apply_belief_delta(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    target, dval = p[0], float(p[1])
    b = _find_belief(world, target)
    if b is None:
        # v0.1 backward compatibility: silently ignore missing beliefs
        return EventApplyOutcome.APPLIED, "", {}
    before = b.prob
    b.prob += dval
    b.clip()
    return EventApplyOutcome.APPLIED, "", {"belief_deltas": [(b.id, b.description, dval, b.prob)]}


def _apply_motif_delta(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    name, args, param, dval = p[0], p[1], p[2], float(p[3])
    key = (name, args)
    if key not in world.motifs:
        world.motifs[key] = Motif(name=name, args=args, params={})
    m = world.motifs[key]
    cur = m.params.get(param, 0.0)
    m.params[param] = max(0.0, min(1.0, cur + dval))
    return EventApplyOutcome.APPLIED, "", {"motif_deltas": [(name, args, param, dval, m.params[param])]}


def _apply_attention_delta(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    actor, target, dval = p[0], p[1], float(p[2])
    rel = world.ensure_relation(actor, target)
    rel.update("attention", dval)
    return EventApplyOutcome.APPLIED, "", {"attention_deltas": [(actor, target, dval)]}


def _apply_hook_create(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    """hook_create(hook_id, hook_type, ...)."""
    # In v0.4, hook creation is delegated back to hookgen.
    # This event kind exists for graph/planning layer to request hooks.
    return EventApplyOutcome.DEFERRED, "hook_creation_delegated_to_hookgen", {}


def _apply_hook_consume(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    hook_id = p[0]
    from .hooks import consume_hook
    if consume_hook(world, hook_id):
        return EventApplyOutcome.APPLIED, "", {"hooks_consumed": [hook_id]}
    return EventApplyOutcome.REJECTED, f"hook_not_found_or_already_consumed({hook_id})", {}


def _apply_hook_decay(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    hook_id, amount = p[0], int(p[1]) if len(p) > 1 else 1
    from .hooks import decay_hook
    if decay_hook(world, hook_id, amount):
        return EventApplyOutcome.APPLIED, "", {"hooks_decayed": [(hook_id, amount)]}
    return EventApplyOutcome.REJECTED, f"hook_decay_failed({hook_id})", {}


def _apply_promote_hook(world: WorldState, p: tuple[Any, ...]) -> tuple[EventApplyOutcome, str, dict]:
    hook_id, amount = p[0], float(p[1]) if len(p) > 1 else 0.1
    hook = world.hooks.get(hook_id)
    if hook:
        hook.priority = min(1.0, hook.priority + amount)
        return EventApplyOutcome.APPLIED, "", {"hooks_promoted": [(hook_id, hook.priority)]}
    return EventApplyOutcome.REJECTED, f"hook_not_found({hook_id})", {}


# ---------- utility ----------


def _location_of(world: WorldState, entity: str) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == entity:
            return f.args[1]
    return ""


def _find_belief(world: WorldState, target: str) -> Belief | None:
    if target in world.beliefs:
        return world.beliefs[target]
    for b in world.beliefs.values():
        if b.description == target:
            return b
    return None
