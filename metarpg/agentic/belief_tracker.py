"""Belief tracker — Bayesian update + collapse (v0.6.6 Primitive C).

Each piece of player-driven evidence nudges a belief probability by a
fixed delta.  When the belief crosses 0.85 it is promoted to a hard
fact; when it drops below 0.15 it is discarded.
"""
from __future__ import annotations

from metarpg.models import Belief, Fact, WorldState


_EVIDENCE_DELTA = 0.15
_PROMOTE_THRESHOLD = 0.85
_DISCARD_THRESHOLD = 0.15


def update_belief(world: WorldState, belief_id: str, evidence_delta: float = _EVIDENCE_DELTA) -> dict[str, Any]:
    """Apply evidence to a single belief. Returns action taken.

    Action keys:
      - "updated": belief probability changed but not yet collapsed
      - "promoted": belief crossed threshold and became a Fact
      - "discarded": belief dropped below threshold and was removed
      - "missing": belief_id not found in world.beliefs
    """
    belief = world.beliefs.get(belief_id)
    if belief is None:
        return {"action": "missing", "belief_id": belief_id}

    old_prob = belief.prob
    belief.prob += evidence_delta
    belief.clip()

    if belief.prob >= _PROMOTE_THRESHOLD:
        # Promote to fact
        fact = Fact(
            predicate=f"belief_{belief_id}",
            args=(belief.description,),
            fact_type="event",
        )
        world.facts.add(fact)
        world.revealed_facts.add(belief_id)
        del world.beliefs[belief_id]
        return {
            "action": "promoted",
            "belief_id": belief_id,
            "old_prob": old_prob,
            "new_fact": str(fact),
        }

    if belief.prob <= _DISCARD_THRESHOLD:
        del world.beliefs[belief_id]
        return {
            "action": "discarded",
            "belief_id": belief_id,
            "old_prob": old_prob,
        }

    return {
        "action": "updated",
        "belief_id": belief_id,
        "old_prob": old_prob,
        "new_prob": belief.prob,
    }


def update_beliefs_from_evidence(world: WorldState, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Batch update. Each evidence dict must have 'belief_id' and optionally
    'delta' (defaults to +0.15) or 'direction' (+1 / -1).
    """
    results: list[dict[str, Any]] = []
    for ev in evidence:
        bid = ev.get("belief_id", "")
        direction = ev.get("direction", 1)
        delta = ev.get("delta", _EVIDENCE_DELTA) * direction
        if bid:
            results.append(update_belief(world, bid, delta))
    return results


def get_belief_surface(world: WorldState) -> list[dict[str, Any]]:
    """Serialize beliefs for the story_packet (probabilistic layer)."""
    return [
        {"id": b.id, "description": b.description, "prob": round(b.prob, 2)}
        for b in world.beliefs.values()
    ]


from typing import Any
