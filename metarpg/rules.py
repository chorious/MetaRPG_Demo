"""Validators and forbidden patterns (PLAN_SONNET §7).

Two surfaces:
  - `validate_patch(world, patch)` evaluates each REQUIRES clause of a patch
    against current canon/knowledge and returns a ValidationResult.
  - `check_forbidden(world, candidate_facts=None)` looks for impossible co-occurrences
    (alive ∧ dead, same agent in two places, entry without access path).
    `candidate_facts` lets a retrodiction be checked *before* canonization.
"""
from __future__ import annotations

from .dsl import parse_predicate
from .models import Fact, Patch, ValidationResult, WorldState


# ---------- requirement clause evaluation ----------

def validate_patch(world: WorldState, patch: Patch) -> ValidationResult:
    """Each REQUIRES line must hold against current state."""
    failed: list[str] = []
    for req in patch.requirements:
        if not _check_requirement(world, req):
            failed.append(req)
    if failed:
        reason = _humanize_failure(failed[0])
        return ValidationResult(ok=False, reason=reason, failed_requirements=failed)
    return ValidationResult(ok=True)


def _check_requirement(world: WorldState, req: str) -> bool:
    name, args = parse_predicate(req)
    if name == "same_location":
        return _same_location(world, args[0], args[1])
    if name == "at":
        return Fact("at", (args[0], args[1])) in world.facts
    if name == "knows":
        # knows(agent, predicate_arg_arg...)  — flatten remaining args into a Fact
        agent = args[0]
        pred = args[1]
        f = Fact(predicate=pred, args=tuple(args[2:]))
        for k in world.knowledge:
            if k.agent == agent and k.fact == f:
                return True
        return False
    if name == "accessible":
        return _accessible(world, args[0])
    if name == "not_sealed":
        return Fact("sealed", (args[0],)) not in world.facts
    if name == "alive":
        return Fact("alive", (args[0],)) in world.facts and Fact("dead", (args[0],)) not in world.facts
    if name == "has_relation":
        rel = world.relations.get((args[0], args[1]))
        return rel is not None
    # default: try to find an exact fact match
    return Fact(predicate=name, args=tuple(args)) in world.facts


def _same_location(world: WorldState, a: str, b: str) -> bool:
    """Both agents share an 'at' location."""
    la = None
    lb = None
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            if f.args[0] == a:
                la = f.args[1]
            if f.args[0] == b:
                lb = f.args[1]
    return la is not None and la == lb


def _accessible(world: WorldState, place: str) -> bool:
    """A place is accessible unless sealed and no access path exists."""
    sealed = Fact("sealed", (place,)) in world.facts
    if not sealed:
        return True
    # any of: holds_key(player, place), permission(player, place), opened(place)
    if Fact("holds_key", ("player", place)) in world.facts:
        return True
    if Fact("permission", ("player", place)) in world.facts:
        return True
    if Fact("opened", (place,)) in world.facts:
        return True
    return False


def _humanize_failure(req: str) -> str:
    """Translate a failed requirement into the PLAN_SONNET-style WHY message."""
    try:
        name, args = parse_predicate(req)
    except ValueError:
        return f"failed_requirement({req})"
    if name == "same_location":
        return f"not_same_location({args[0]},{args[1]})"
    if name == "at":
        return f"missing_required_location({args[0]},{args[1]})"
    if name == "knows":
        agent = args[0]
        return f"speaker_does_not_know_required_fact({agent})"
    if name == "accessible":
        return f"location_inaccessible({args[0]})"
    if name == "not_sealed":
        return f"location_sealed({args[0]})"
    return f"failed_requirement({req})"


# ---------- forbidden pattern check ----------

def check_forbidden(
    world: WorldState,
    candidate_facts: list[Fact] | None = None,
) -> ValidationResult:
    """Return ok=False if the (current ∪ candidate) fact set hits a forbidden pattern.

    Used by retrodiction to dry-run a candidate canon delta before committing.
    """
    fset: set[Fact] = set(world.facts)
    if candidate_facts:
        fset.update(candidate_facts)

    by_pred: dict[str, list[Fact]] = {}
    for f in fset:
        by_pred.setdefault(f.predicate, []).append(f)

    # 1. alive(X) ∧ dead(X)
    alive_xs = {f.args[0] for f in by_pred.get("alive", []) if f.args}
    dead_xs = {f.args[0] for f in by_pred.get("dead", []) if f.args}
    overlap = alive_xs & dead_xs
    if overlap:
        x = sorted(overlap)[0]
        return ValidationResult(ok=False, reason=f"forbidden_alive_and_dead({x})")

    # 2. at(X, A) ∧ at(X, B) with A != B
    at_by_agent: dict[str, set[str]] = {}
    for f in by_pred.get("at", []):
        if len(f.args) == 2:
            at_by_agent.setdefault(f.args[0], set()).add(f.args[1])
    for agent, places in at_by_agent.items():
        if len(places) > 1:
            ps = sorted(places)
            return ValidationResult(
                ok=False, reason=f"forbidden_two_locations({agent},{ps[0]},{ps[1]})"
            )

    # 3. entered(X, P, T) without access path when P sealed
    sealed_places = {f.args[0] for f in by_pred.get("sealed", []) if f.args}
    for f in by_pred.get("entered", []):
        if len(f.args) >= 2 and f.args[1] in sealed_places:
            X, P = f.args[0], f.args[1]
            has_access = (
                Fact("holds_key", (X, P)) in fset
                or Fact("permission", (X, P)) in fset
                or Fact("opened", (P,)) in fset
                or Fact("found_passage", (X, P)) in fset
            )
            if not has_access:
                return ValidationResult(
                    ok=False, reason=f"forbidden_entry_without_access({X},{P})"
                )

    return ValidationResult(ok=True)
