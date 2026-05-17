"""Scene expansion — v0.5.

Controlled local surface generation when entering a new scene.
Separates hard admitted, soft visible, and latent compressed details.
"""
from __future__ import annotations

from .affordance import AffordanceCandidate
from .expansion_budget import Budget
from .models import Claim, ClaimStatus, ProposedEffect, WorldState


def expand_scene(world: WorldState, location: str, budget: Budget) -> list[AffordanceCandidate]:
    """Generate scene surface affordances, tiered by hardness.

    Returns candidates only — no direct state mutation.
    """
    candidates: list[AffordanceCandidate] = []

    # Hard: exits and explicit anchors
    candidates.extend(_hard_surface(world, location))

    # Soft: visible NPCs and low-impact objects
    if budget.allows_hard_mutation():
        candidates.extend(_soft_surface(world, location, budget))

    # Latent: implied but not materialized
    if budget.class_.value in ("medium", "large", "emergency"):
        candidates.extend(_latent_surface(world, location))

    return candidates


def _hard_surface(world: WorldState, loc: str) -> list[AffordanceCandidate]:
    """Hard admitted: exits, explicitly visible anchors."""
    hard: list[AffordanceCandidate] = []

    # Exits (simplified: all locations except current are exits)
    for place in world.locations:
        if place != loc:
            hard.append(
                AffordanceCandidate(
                    id=f"exit_to_{place}", kind="move_through", actor="player", anchor=place,
                    action_template=f"go_to_{place}", source_frontier="scene",
                    support_claims=[
                        Claim("destination_exists", (place,), ClaimStatus.UNKNOWN, ""),
                        Claim("connected_or_traversable", (loc, place), ClaimStatus.UNKNOWN, ""),
                    ],
                    proposed_effects=[
                        ProposedEffect("travel", ("player", loc, place), 3),
                    ],
                    score=0.5,
                    persistence="session",
                )
            )

    return hard


def _soft_surface(world: WorldState, loc: str, budget: Budget) -> list[AffordanceCandidate]:
    """Soft visible: NPCs, low-impact objects with provenance."""
    soft: list[AffordanceCandidate] = []

    # NPCs at this location
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if place == loc and entity in world.npcs:
                soft.append(
                    AffordanceCandidate(
                        id=f"npc_{entity}", kind="talk_about", actor="player", anchor=entity,
                        action_template=f"talk_to_{entity}", source_frontier="scene",
                        support_claims=[Claim("same_location", ("player", entity), ClaimStatus.ACCEPTED, "")],
                        proposed_effects=[ProposedEffect("dialogue", (f"player_spoke_to_{entity}",), 0)],
                        score=0.6,
                        persistence="session",
                    )
                )

    # Plausible objects (from item_plausibility)
    items = world.item_plausibility.get(loc, set())
    for item in items:
        if budget.max_hard_facts > 0:
            soft.append(
                AffordanceCandidate(
                    id=f"obj_{item}", kind="inspect", actor="player", anchor=item,
                    action_template=f"inspect_{item}", source_frontier="scene",
                    support_claims=[Claim("item_plausible", (item, loc), ClaimStatus.ACCEPTED, "")],
                    proposed_effects=[ProposedEffect("observe", (f"saw_{item}",), 0)],
                    score=0.4,
                    persistence="transient",
                )
            )

    return soft


def _latent_surface(world: WorldState, loc: str) -> list[AffordanceCandidate]:
    """Latent compressed: implied but not materialized until touched."""
    latent: list[AffordanceCandidate] = []

    # Latent hooks related to this place
    for hook in world.hooks.values():
        if hook.consumed:
            continue
        if loc in hook.places or loc in hook.source_events:
            latent.append(
                AffordanceCandidate(
                    id=f"latent_hook_{hook.id}", kind="follow_up_hook", actor="player",
                    anchor=hook.id, action_template=f"follow_up_{hook.id}", source_frontier="scene",
                    support_claims=[Claim("hook_active", (hook.id,), ClaimStatus.UNKNOWN, "")],
                    proposed_effects=[],
                    score=hook.priority * 0.5,
                    persistence="transient",
                )
            )

    return latent
