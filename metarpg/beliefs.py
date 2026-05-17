"""Belief / latent layer updates (PLAN_SONNET §4.4, §8).

Beliefs are stored as probabilities in [0, 1]. Updates are applied as additive
deltas modulated by the active narrative motifs whose args appear in the belief
description. The modulation factor is bounded so deltas can be amplified or
damped but cannot flip sign.

Crossing a threshold (default 0.80) makes a belief eligible for a retrodiction
proposal — see `retrodict.py`.
"""
from __future__ import annotations

from .models import Belief, Motif, WorldState

DEFAULT_RETRO_THRESHOLD = 0.80

# Modulation: a motif touches a belief iff one of its args is a substring of
# the belief description. Effective factor = clip(1 + 0.5 * mean(sig), 0.5, 1.5)
# where sig is the average param magnitude of all touching motifs.
_MOD_MIN = 0.5
_MOD_MAX = 1.5


def modulation_factor(world: WorldState, belief: Belief) -> float:
    """Compute how the active motifs amplify/damp a delta to this belief."""
    matching: list[Motif] = []
    for m in world.motifs.values():
        if any(arg in belief.description for arg in m.args):
            matching.append(m)
    if not matching:
        return 1.0
    sig = 0.0
    n = 0
    for m in matching:
        for v in m.params.values():
            sig += v
            n += 1
    if n == 0:
        return 1.0
    mean_sig = sig / n
    factor = 1.0 + 0.5 * mean_sig
    return max(_MOD_MIN, min(_MOD_MAX, factor))


def apply_delta(
    world: WorldState,
    target: str,
    raw_delta: float,
) -> tuple[Belief, float, float] | None:
    """Apply a modulated belief delta. Returns (belief, applied_delta, factor) or None."""
    b = _resolve_belief(world, target)
    if b is None:
        return None
    f = modulation_factor(world, b)
    applied = raw_delta * f
    b.prob = max(0.0, min(1.0, b.prob + applied))
    return b, applied, f


def _resolve_belief(world: WorldState, target: str) -> Belief | None:
    if target in world.beliefs:
        return world.beliefs[target]
    for b in world.beliefs.values():
        if b.description == target:
            return b
    return None


def threshold_crossings(
    world: WorldState,
    previous: dict[str, float],
    threshold: float = DEFAULT_RETRO_THRESHOLD,
) -> list[Belief]:
    """Beliefs that crossed the threshold from below this turn.

    `previous` is a snapshot of {belief.id: belief.prob} taken before the turn's
    deltas were applied.
    """
    out: list[Belief] = []
    for b in world.beliefs.values():
        old = previous.get(b.id, 0.0)
        if old < threshold <= b.prob:
            out.append(b)
    return out


def snapshot_probs(world: WorldState) -> dict[str, float]:
    """Capture {id: prob} for later comparison."""
    return {b.id: b.prob for b in world.beliefs.values()}
