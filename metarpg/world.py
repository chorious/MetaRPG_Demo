"""Runtime state container, local-slice extraction, patch application, and
cold-archive / canon-log writers.

The local slice is the heart of PLAN_SONNET §1:

    GlobalJudge(history, action) ~= LocalJudge(reasonability_slice, action)

A slice is built from a set of touched entities (drawn from the action's args
plus 'player'). Only facts/knowledge/relations/motifs/beliefs that mention any
touched entity make it into the slice.
"""
from __future__ import annotations

import json
import os
from typing import Iterable

from .models import (
    Action,
    Belief,
    Effect,
    Fact,
    Knowledge,
    LocalSlice,
    Motif,
    Patch,
    Relation,
    WorldState,
)


# ---------- touched-entity extraction ----------

def touched_from_action(action: Action, world: WorldState) -> set[str]:
    """The set of entities relevant to this action."""
    t: set[str] = {"player"}
    for a in action.args:
        if a:
            t.add(a)
    return t


# ---------- local slice ----------

def extract_local_slice(world: WorldState, touched: set[str]) -> LocalSlice:
    """Pull only entities/relations/motifs/beliefs that mention any touched entity."""
    def hits(args: Iterable[str]) -> bool:
        return any(a in touched for a in args)

    facts = [f for f in world.facts if hits(f.args)]
    knowledge = [k for k in world.knowledge if k.agent in touched or hits(k.fact.args)]
    relations = [
        r for (_, _), r in world.relations.items()
        if r.from_agent in touched or r.to_agent in touched
    ]
    motifs = [m for m in world.motifs.values() if hits(m.args)]
    beliefs = [
        b for b in world.beliefs.values()
        if any(t in b.description for t in touched)
    ]
    return LocalSlice(
        touched=set(touched),
        facts=facts,
        knowledge=knowledge,
        relations=relations,
        motifs=motifs,
        beliefs=beliefs,
        frontier=list(world.frontier),
    )


# ---------- patch application ----------

def apply_patch(world: WorldState, patch: Patch) -> dict[str, object]:
    """Apply all effects of a validated patch via v0.4 apply_event layer.

    Returns a delta summary with the same shape as before, so callers
    (engine, tests, renderer) do not need to change.
    """
    from .apply_event import apply_events
    from .events import AdmittedEvent

    events = [AdmittedEvent.from_effect(eff) for eff in patch.effects]
    report = apply_events(world, events)
    delta = report.merged_delta

    # Ensure all standard keys exist for backward compatibility
    for key in (
        "events", "transient_events", "observations", "rel_deltas",
        "belief_deltas", "facts_added", "facts_removed",
        "knowledge_added", "motif_deltas", "objects_added",
        "objects_removed", "risk_flags", "attention_deltas",
        "hooks_consumed", "hooks_decayed", "hooks_promoted",
    ):
        if key not in delta:
            delta[key] = []
    return delta


def _find_belief(world: WorldState, target: str) -> Belief | None:
    """Resolve a belief by id (H1) or description (mara_knows_recent_entry)."""
    if target in world.beliefs:
        return world.beliefs[target]
    for b in world.beliefs.values():
        if b.description == target:
            return b
    return None


# ---------- cold archive + canon log ----------

def archive_event(
    world: WorldState,
    kind: str,
    text: str,
    touched: set[str] | None = None,
) -> None:
    """Append a JSONL event to the cold archive. Never read back in normal turns."""
    if not world.archive_path:
        return
    os.makedirs(os.path.dirname(world.archive_path), exist_ok=True)
    record = {
        "turn": world.turn,
        "kind": kind,
        "text": text,
        "touched": sorted(touched) if touched else [],
    }
    with open(world.archive_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_canon(world: WorldState, line: str) -> None:
    """Append a line to the canon delta log."""
    if not world.canon_log_path:
        return
    os.makedirs(os.path.dirname(world.canon_log_path), exist_ok=True)
    with open(world.canon_log_path, "a", encoding="utf-8") as f:
        f.write(f"T{world.turn} {line}\n")
