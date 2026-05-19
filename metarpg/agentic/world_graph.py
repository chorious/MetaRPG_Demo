"""WorldGraph adapter — thin wrapper over WorldState for v0.7.0.

Full migration to a native WorldGraph dataclass is deferred to v0.7.1+.
This module provides a seed-to-world factory and ensures v0.7.0 fields exist.
"""
from __future__ import annotations

from metarpg.agentic.seed_loader import WorldSeed
from metarpg.models import Belief, Fact, WorldState


def world_from_seed(seed: WorldSeed) -> WorldState:
    """Build a WorldState from a loaded WorldSeed."""
    world = WorldState()
    world.turn = seed.time.get("turn", 0)
    world.world_time = {
        "turn": seed.time.get("turn", 0),
        "hour": 12,
        "day": 1,
    }

    for f in seed.canon_facts:
        pred = f.get("predicate", "")
        args = tuple(f.get("args", []))
        if pred and args:
            world.facts.add(Fact(pred, args, fact_type=""))

    for loc_id in seed.locations:
        world.locations.add(loc_id)

    for ent_id, ent in seed.entities.items():
        if ent.get("kind") == "npc":
            world.npcs.add(ent_id)

    for item_id, item in seed.items.items():
        owner = item.get("owner", "")
        if owner:
            world.facts.add(Fact("has", (owner, item_id)))
        loc = item.get("location", "")
        if loc:
            world.facts.add(Fact("at", (item_id, loc)))

    for bid, b in seed.beliefs.items():
        world.beliefs[bid] = Belief(
            id=bid,
            description=b.get("proposition", ""),
            prob=b.get("probability", 0.5),
        )

    # v0.7.0 extensions (not in legacy models.py)
    world.events = []
    world.utterances = []
    world.hints = {}
    world.affordances = {}
    # v0.7.1: pre-load seed hook IDs so Validator can check existence
    world._hook_status = {
        hid: hook.get("status", "dormant")
        for hid, hook in seed.active_hooks.items()
    }
    world.hidden_truths = dict(seed.hidden_truths)

    return world
