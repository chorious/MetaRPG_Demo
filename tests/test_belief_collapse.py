"""Tests for belief_tracker — Bayesian update + collapse (v0.6.6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.belief_tracker import (
    get_belief_surface,
    update_belief,
    update_beliefs_from_evidence,
)
from metarpg.models import Belief, Fact, WorldState


def _world_with_belief(prob: float) -> WorldState:
    w = WorldState()
    w.beliefs["mara_knows_mine"] = Belief(
        id="mara_knows_mine",
        description="Mara knows about the old mine",
        prob=prob,
    )
    return w


def test_update_nudges_probability() -> None:
    w = _world_with_belief(0.45)
    result = update_belief(w, "mara_knows_mine", 0.15)
    assert result["action"] == "updated"
    assert result["new_prob"] == 0.60


def test_promote_to_fact_at_0_85() -> None:
    w = _world_with_belief(0.75)
    result = update_belief(w, "mara_knows_mine", 0.15)
    assert result["action"] == "promoted"
    # Belief removed from world.beliefs
    assert "mara_knows_mine" not in w.beliefs
    # Fact added
    assert any("mara_knows_mine" in str(f) for f in w.facts)
    # revealed_facts tracked
    assert "mara_knows_mine" in w.revealed_facts


def test_discard_below_0_15() -> None:
    w = _world_with_belief(0.20)
    result = update_belief(w, "mara_knows_mine", -0.10)
    assert result["action"] == "discarded"
    assert "mara_knows_mine" not in w.beliefs


def test_missing_belief_returns_missing() -> None:
    w = WorldState()
    result = update_belief(w, "nonexistent", 0.15)
    assert result["action"] == "missing"


def test_batch_update_from_evidence() -> None:
    w = _world_with_belief(0.50)
    evidence = [
        {"belief_id": "mara_knows_mine", "delta": 0.15},
        {"belief_id": "mara_knows_mine", "delta": 0.15},
    ]
    results = update_beliefs_from_evidence(w, evidence)
    # 0.50 + 0.15 + 0.15 = 0.80, still below 0.85
    assert len(results) == 2
    assert results[-1]["action"] == "updated"
    assert results[-1]["new_prob"] == 0.80


def test_belief_surface_format() -> None:
    w = _world_with_belief(0.45)
    surface = get_belief_surface(w)
    assert len(surface) == 1
    assert surface[0]["id"] == "mara_knows_mine"
    assert "prob" in surface[0]


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
