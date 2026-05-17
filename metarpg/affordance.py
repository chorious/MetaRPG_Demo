"""Affordance candidate layer — v0.5.

Defines affordance candidates generated from touched frontiers.
An affordance is a possible action that can be imagined, validated,
and executed in a given local context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .frontier import Frontier
from .models import Claim, ProposedEffect


@dataclass
class AffordanceCandidate:
    """One possible action derived from a frontier."""

    id: str
    kind: str
    actor: str
    anchor: str
    action_template: str
    source_frontier: str
    support_claims: list[Claim] = field(default_factory=list)
    proposed_effects: list[ProposedEffect] = field(default_factory=list)
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    persistence: str = "transient"  # transient | session | canon_candidate
    risk: float = 0.0


# Common affordance kinds
AFFORDANCE_KINDS: set[str] = {
    "inspect", "move_through", "talk_about", "use_as_tool",
    "force_open", "hide", "listen", "buy_or_trade",
    "ask_for_help", "threaten", "persuade", "report_event",
    "follow_up_hook", "materialize_object", "observe_reaction",
}
