"""Belief update + modulation + threshold tests."""
from __future__ import annotations

from metarpg import beliefs
from metarpg.models import Belief, Motif, WorldState


def _world_with_belief(prob: float, description: str = "mara_knows_recent_entry") -> WorldState:
    w = WorldState()
    w.beliefs["H1"] = Belief("H1", description, prob)
    return w


def test_apply_delta_no_motif_modulation_is_one():
    w = _world_with_belief(0.45)
    result = beliefs.apply_delta(w, "mara_knows_recent_entry", 0.10)
    assert result is not None
    b, applied, factor = result
    assert factor == 1.0
    assert abs(applied - 0.10) < 1e-9
    assert abs(b.prob - 0.55) < 1e-9


def test_apply_delta_motif_amplifies():
    w = _world_with_belief(0.45)
    w.motifs[("forbidden_place", ("mara_knows_recent_entry",))] = Motif(
        "forbidden_place", ("mara_knows_recent_entry",), {"lure": 0.62}
    )
    result = beliefs.apply_delta(w, "mara_knows_recent_entry", 0.10)
    assert result is not None
    _, applied, factor = result
    assert factor > 1.0
    assert applied > 0.10


def test_threshold_crossing_detected():
    w = _world_with_belief(0.75)
    prev = beliefs.snapshot_probs(w)
    beliefs.apply_delta(w, "mara_knows_recent_entry", 0.10)
    crossings = beliefs.threshold_crossings(w, prev)
    assert len(crossings) == 1
    assert crossings[0].description == "mara_knows_recent_entry"


def test_threshold_not_crossed_when_already_above():
    w = _world_with_belief(0.85)
    prev = beliefs.snapshot_probs(w)
    beliefs.apply_delta(w, "mara_knows_recent_entry", 0.05)
    crossings = beliefs.threshold_crossings(w, prev)
    assert crossings == []


def test_belief_prob_clipped():
    w = _world_with_belief(0.95)
    beliefs.apply_delta(w, "mara_knows_recent_entry", 0.50)
    assert w.beliefs["H1"].prob == 1.0


def test_unknown_target_returns_none():
    w = _world_with_belief(0.45)
    assert beliefs.apply_delta(w, "no_such_belief", 0.10) is None
