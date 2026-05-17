"""Affordance expansion — v0.5.

Generate candidate affordances from touched frontiers.
Deterministic/heuristic first; LLM-assisted later.
"""
from __future__ import annotations

from .affordance import AffordanceCandidate
from .frontier import Frontier, FrontierKind
from .models import Claim, ClaimStatus, ProposedEffect, WorldState


def generate_candidates(world: WorldState, frontiers: list[Frontier], actor: str = "player") -> list[AffordanceCandidate]:
    """Generate affordance candidates from touched frontiers."""
    candidates: list[AffordanceCandidate] = []
    seen: set[str] = set()

    for f in frontiers:
        new = _candidates_for_frontier(world, f, actor)
        for c in new:
            key = f"{c.kind}:{c.anchor}"
            if key not in seen:
                seen.add(key)
                candidates.append(c)

    return candidates


def _candidates_for_frontier(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """Dispatch to frontier-kind-specific generators."""
    if f.kind == FrontierKind.SCENE_BOUNDARY:
        return _scene_boundary_candidates(world, f, actor)
    if f.kind == FrontierKind.SALIENT_OBJECT:
        return _salient_object_candidates(world, f, actor)
    if f.kind == FrontierKind.UNQUERIED_NPC:
        return _unqueried_npc_candidates(world, f, actor)
    if f.kind == FrontierKind.ACTIVE_SOCIAL_TENSION:
        return _social_tension_candidates(world, f, actor)
    if f.kind == FrontierKind.LATENT_HOOK:
        return _latent_hook_candidates(world, f, actor)
    if f.kind == FrontierKind.NEW_TOOL_POSSIBILITY:
        return _tool_possibility_candidates(world, f, actor)
    if f.kind == FrontierKind.THREAT_BOUNDARY:
        return _threat_boundary_candidates(world, f, actor)
    if f.kind == FrontierKind.UNKNOWN_CAUSAL_PATH:
        return _causal_path_candidates(world, f, actor)
    return []


def _scene_boundary_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """Entering a new scene: inspect, listen, move."""
    loc = f.location or f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_inspect", kind="inspect", actor=actor, anchor=loc,
            action_template=f"inspect_{loc}", source_frontier=f.id,
            support_claims=[Claim("destination_exists", (loc,), ClaimStatus.UNKNOWN, "")],
            proposed_effects=[ProposedEffect("observe", (f"scene_{loc}",), 0)],
            score=0.6,
        ),
        AffordanceCandidate(
            id=f"{f.id}_listen", kind="listen", actor=actor, anchor=loc,
            action_template=f"listen_to_{loc}", source_frontier=f.id,
            support_claims=[Claim("same_location", (actor, loc), ClaimStatus.UNKNOWN, "")],
            proposed_effects=[ProposedEffect("observe", (f"ambient_{loc}",), 0)],
            score=0.5,
        ),
    ]


def _salient_object_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """A notable object: inspect, use_as_tool, pick_up."""
    obj = f.anchor_entity
    loc = f.location or _actor_location(world, actor)
    candidates: list[AffordanceCandidate] = [
        AffordanceCandidate(
            id=f"{f.id}_inspect", kind="inspect", actor=actor, anchor=obj,
            action_template=f"inspect_{obj}", source_frontier=f.id,
            support_claims=[
                Claim("object_exists", (obj,), ClaimStatus.UNKNOWN, ""),
                Claim("same_location", (actor, obj), ClaimStatus.UNKNOWN, ""),
            ],
            proposed_effects=[ProposedEffect("observe", (f"inspected_{obj}",), 0)],
            score=0.65,
        ),
    ]
    # If object is movable, add pick_up
    tags = world.object_tags.get(obj, set())
    if "movable" in tags:
        candidates.append(
            AffordanceCandidate(
                id=f"{f.id}_pickup", kind="materialize_object", actor=actor, anchor=obj,
                action_template=f"pick_up_{obj}", source_frontier=f.id,
                support_claims=[
                    Claim("can_materialize", (obj, loc, "1"), ClaimStatus.UNKNOWN, ""),
                    Claim("movable", (obj,), ClaimStatus.UNKNOWN, ""),
                ],
                proposed_effects=[
                    ProposedEffect("add_object", (obj, loc), 2),
                ],
                score=0.55,
            )
        )
    return candidates


def _unqueried_npc_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """An NPC not yet engaged: talk, ask, observe."""
    npc = f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_talk", kind="talk_about", actor=actor, anchor=npc,
            action_template=f"talk_to_{npc}", source_frontier=f.id,
            support_claims=[
                Claim("same_location", (actor, npc), ClaimStatus.UNKNOWN, ""),
                Claim("can_speak_to", (actor, npc), ClaimStatus.UNKNOWN, ""),
            ],
            proposed_effects=[
                ProposedEffect("dialogue", (f"player_spoke_to_{npc}",), 0),
                ProposedEffect("rel_delta", (npc, actor, "trust", 0.01), 1),
            ],
            score=0.7,
        ),
        AffordanceCandidate(
            id=f"{f.id}_observe", kind="observe_reaction", actor=actor, anchor=npc,
            action_template=f"observe_{npc}", source_frontier=f.id,
            support_claims=[Claim("same_location", (actor, npc), ClaimStatus.UNKNOWN, "")],
            proposed_effects=[ProposedEffect("observe", (f"observed_{npc}",), 0)],
            score=0.5,
        ),
    ]


def _social_tension_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """Active tension: threaten, persuade, help, de-escalate."""
    target = f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_persuade", kind="persuade", actor=actor, anchor=target,
            action_template=f"persuade_{target}", source_frontier=f.id,
            support_claims=[
                Claim("same_location", (actor, target), ClaimStatus.UNKNOWN, ""),
                Claim("can_speak_to", (actor, target), ClaimStatus.UNKNOWN, ""),
            ],
            proposed_effects=[ProposedEffect("rel_delta", (target, actor, "trust", 0.05), 1)],
            score=0.6,
        ),
        AffordanceCandidate(
            id=f"{f.id}_threaten", kind="threaten", actor=actor, anchor=target,
            action_template=f"threaten_{target}", source_frontier=f.id,
            support_claims=[
                Claim("same_location", (actor, target), ClaimStatus.UNKNOWN, ""),
                Claim("can_threaten", (actor, target, "bare_hands"), ClaimStatus.UNKNOWN, ""),
            ],
            proposed_effects=[
                ProposedEffect("rel_delta", (target, actor, "fear", 0.08), 1),
                ProposedEffect("rel_delta", (target, actor, "trust", -0.05), 1),
            ],
            score=0.45,
            risk=0.3,
        ),
    ]


def _latent_hook_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """A pending hook: report_event, follow_up."""
    hook_topic = f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_report", kind="report_event", actor=actor, anchor=hook_topic,
            action_template=f"report_{hook_topic}", source_frontier=f.id,
            support_claims=[Claim("player_knows", (hook_topic,), ClaimStatus.UNKNOWN, "")],
            proposed_effects=[ProposedEffect("transient_event", (f"player_reported_{hook_topic}",), 0)],
            score=0.55,
        ),
    ]


def _tool_possibility_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """A potential tool use: use_as_tool, force_open."""
    obj = f.anchor_entity
    loc = f.location or _actor_location(world, actor)
    return [
        AffordanceCandidate(
            id=f"{f.id}_use_tool", kind="use_as_tool", actor=actor, anchor=obj,
            action_template=f"use_{obj}_as_tool", source_frontier=f.id,
            support_claims=[
                Claim("has_or_near", (actor, obj), ClaimStatus.UNKNOWN, ""),
                Claim("use_as_tool", (obj, "wedge"), ClaimStatus.UNKNOWN, ""),
            ],
            proposed_effects=[ProposedEffect("transient_event", (f"player_used_{obj}",), 0)],
            score=0.6,
        ),
    ]


def _threat_boundary_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """A threat: hide, flee, confront."""
    threat = f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_hide", kind="hide", actor=actor, anchor=threat,
            action_template=f"hide_from_{threat}", source_frontier=f.id,
            support_claims=[Claim("same_location", (actor, threat), ClaimStatus.UNKNOWN, "")],
            proposed_effects=[ProposedEffect("transient_event", (f"player_hid_from_{threat}",), 0)],
            score=0.5,
        ),
    ]


def _causal_path_candidates(world: WorldState, f: Frontier, actor: str) -> list[AffordanceCandidate]:
    """An unknown cause: investigate, ask, recall."""
    topic = f.anchor_entity
    return [
        AffordanceCandidate(
            id=f"{f.id}_investigate", kind="inspect", actor=actor, anchor=topic,
            action_template=f"investigate_{topic}", source_frontier=f.id,
            support_claims=[],
            proposed_effects=[ProposedEffect("observe", (f"investigated_{topic}",), 0)],
            score=0.5,
        ),
    ]


# ---------- utility ----------

def _actor_location(world: WorldState, actor: str) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == actor:
            return f.args[1]
    return ""
