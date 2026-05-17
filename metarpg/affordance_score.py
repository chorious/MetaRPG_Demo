"""Affordance scoring — v0.5.

Score candidates using current world state, meta act, and graph.
"""
from __future__ import annotations

from .affordance import AffordanceCandidate
from .models import MetaAct, WorldState


def score_affordance(candidate: AffordanceCandidate, world: WorldState, meta: MetaAct) -> float:
    """Score a single candidate. Returns 0.0–1.0."""
    breakdown: dict[str, float] = {}

    # Player attention: did player point at this thing?
    text = meta.raw_text.lower()
    if candidate.anchor in text or candidate.kind in text:
        breakdown["player_attention"] = 0.25
    else:
        breakdown["player_attention"] = 0.05

    # Goal relevance: does this help implied goal?
    # Simple heuristic: movement-related candidates score higher if player wants to move
    if any(k in text for k in ("去", "go", "move", "enter", "进入")) and candidate.kind in ("move_through", "inspect"):
        breakdown["goal_relevance"] = 0.15
    elif any(k in text for k in ("问", "ask", "talk", "告诉")) and candidate.kind == "talk_about":
        breakdown["goal_relevance"] = 0.15
    elif any(k in text for k in ("找", "find", "pick", "use")) and candidate.kind in ("materialize_object", "use_as_tool"):
        breakdown["goal_relevance"] = 0.15
    else:
        breakdown["goal_relevance"] = 0.05

    # Uncertainty reduction: candidates with more claims = more clarifying
    claim_count = len(candidate.support_claims)
    breakdown["uncertainty_reduction"] = min(0.1, claim_count * 0.02)

    # Validation confidence: can code judge it reliably?
    known_claims = sum(1 for c in candidate.support_claims if c.name in {
        "same_location", "can_speak_to", "object_exists", "can_materialize",
        "has_or_near", "use_as_tool", "can_threaten", "player_knows",
    })
    breakdown["validation_confidence"] = min(0.15, known_claims * 0.03)

    # Contradiction risk: lower is better
    risk_penalty = candidate.risk * 0.1
    breakdown["contradiction_risk"] = -risk_penalty

    # Canon pollution: hard-fact candidates are slightly penalized
    hard_effects = sum(1 for e in candidate.proposed_effects if e.impact >= 2)
    breakdown["canon_pollution"] = -min(0.05, hard_effects * 0.02)

    total = sum(breakdown.values())
    candidate.score = max(0.0, min(1.0, total))
    candidate.score_breakdown = breakdown
    return candidate.score


def rank_affordances(candidates: list[AffordanceCandidate], max_count: int) -> list[AffordanceCandidate]:
    """Sort by score descending and return top N."""
    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return ranked[:max_count]
