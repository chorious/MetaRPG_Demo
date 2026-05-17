"""Retrodiction proposal + validation + canonization (PLAN_SONNET §8).

When a belief crosses the retrodiction threshold, we look up a template that
says "if this hypothesis is true, here are the cause facts that explain it and
the observations they account for". The template is dry-run through the
forbidden-pattern check; only if it survives unchanged does it become canon.
"""
from __future__ import annotations

from .models import Fact, Retropath, ValidationResult, WorldState
from .rules import check_forbidden
from .world import record_canon


# Belief description -> Retropath template.
# Templates are scenario-local in spirit but live here for v0.1 simplicity.
_TEMPLATES: dict[str, Retropath] = {
    "mara_knows_recent_entry": Retropath(
        target="mara_knows_recent_entry",
        causes=[
            Fact("saw", ("mara", "recent_entry", "day_minus_2")),
        ],
        explains=["mara_evasive_about_mine"],
    ),
    "mara_entered_mine": Retropath(
        target="mara_entered_mine",
        causes=[
            Fact("found_passage", ("mara", "old_mine")),
            Fact("entered", ("mara", "old_mine", "day_minus_2")),
        ],
        explains=["mara_evasive_about_mine", "mara_knows_recent_entry"],
    ),
    "rusk_pressures_mara": Retropath(
        target="rusk_pressures_mara",
        causes=[
            Fact("mara_saw_rusk_near_mine", ("day_minus_2",)),
            Fact("rusk_threatened_mara", ("day_minus_1",)),
        ],
        explains=["mara_evasive_about_mine"],
    ),
    "iven_alive_in_mine": Retropath(
        target="iven_alive_in_mine",
        causes=[
            Fact("alive", ("iven",)),
            Fact("found_passage", ("iven", "old_mine")),
            Fact("entered", ("iven", "old_mine", "day_minus_3")),
        ],
        explains=["missing(iven)"],
    ),
    "iven_dead_and_hidden": Retropath(
        target="iven_dead_and_hidden",
        causes=[
            Fact("dead", ("iven",)),
            Fact("hidden_body", ("iven", "old_mine")),
        ],
        explains=["missing(iven)"],
    ),
}


def register_template(target: str, rp: Retropath) -> None:
    """Allow scenarios to extend the retropath table without touching core."""
    _TEMPLATES[target] = rp


def propose(
    world: WorldState, belief_description: str, templates: dict[str, Retropath] | None = None
) -> Retropath | None:
    """Look up the cause chain for a high-confidence belief.

    If `templates` is provided (from scenario hooks), use that isolated set.
    Otherwise fall back to the global default table.
    """
    table = templates if templates is not None else _TEMPLATES
    return table.get(belief_description)


def validate(world: WorldState, rp: Retropath) -> ValidationResult:
    """Dry-run candidate facts through forbidden-pattern check."""
    return check_forbidden(world, candidate_facts=list(rp.causes))


def canonize(world: WorldState, rp: Retropath) -> list[Fact]:
    """Commit cause facts to canon (idempotent). Returns the newly added facts."""
    added: list[Fact] = []
    for f in rp.causes:
        if f not in world.facts:
            world.facts.add(f)
            added.append(f)
            record_canon(world, f"+ {f} (retro:{rp.target})")
    return added
