"""UPF-inspired event protocol — v0.4.

AdmittedEvent taxonomy and EventApplyOutcome discipline.

Do not replace current Effect immediately. This module adds an adapter layer:
  ProposedEffect -> AdmittedEvent -> StateDelta

Borrowed from UPF:
  - Outcome discipline: applied / rejected / deferred
  - Event categorization: narrative-only vs state-mutation vs graph-planning
  - Source/provenance tracking for every admitted event
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import Effect


class EventApplyOutcome(Enum):
    """Three-state outcome for every event application attempt."""

    APPLIED = "applied"       # state mutated successfully
    REJECTED = "rejected"     # rule or validation blocked application
    DEFERRED = "deferred"     # plausible but missing context; may retry later


@dataclass
class AdmittedEvent:
    """An event that has passed claim validation and is ready for state application.

    This is v0.4's structured-event shape. It wraps the simpler v0.1 Effect
    with source tracking and deferred/rejected outcome support.
    """

    kind: str
    payload: tuple[Any, ...]
    source: str = ""          # e.g. "hook:H_guard_mine_report" or "hypothesis:composite_act"
    provenance: str = ""      # e.g. "dynamic_action", "predefined", "retrodiction", "plot_repair"

    @classmethod
    def from_effect(cls, effect: Effect, source: str = "", provenance: str = "") -> AdmittedEvent:
        """Adapter: convert existing Effect to AdmittedEvent."""
        return cls(kind=effect.kind, payload=effect.payload, source=source, provenance=provenance)

    def to_effect(self) -> Effect:
        """Adapter: convert back to Effect for backward compatibility."""
        from .models import Effect
        return Effect(kind=self.kind, payload=self.payload)


# ---------- event taxonomy ----------

NARRATIVE_EVENT_KINDS: set[str] = {
    "dialogue",
    "transient_event",
    "observation",
    "canon_event",
}

STATE_MUTATION_KINDS: set[str] = {
    "travel",
    "add_fact",
    "remove_fact",
    "add_knowledge",
    "add_object",
    "remove_object",
    "relationship_change",
    "belief_delta",
    "hook_create",
    "hook_consume",
    "hook_decay",
    "flag_set",
    "attention_delta",
    "risk_flag",
    "motif_delta",
}

GRAPH_PLANNING_KINDS: set[str] = {
    "motif_activate",
    "motif_resolve",
    "plot_thread_open",
    "plot_thread_advance",
    "plot_thread_close",
}

ALL_EVENT_KINDS: set[str] = NARRATIVE_EVENT_KINDS | STATE_MUTATION_KINDS | GRAPH_PLANNING_KINDS


def event_category(kind: str) -> str:
    """Return 'narrative' | 'state' | 'graph' | 'unknown' for a given event kind."""
    if kind in NARRATIVE_EVENT_KINDS:
        return "narrative"
    if kind in STATE_MUTATION_KINDS:
        return "state"
    if kind in GRAPH_PLANNING_KINDS:
        return "graph"
    return "unknown"
