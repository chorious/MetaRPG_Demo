"""Patch assembler tests."""
from __future__ import annotations

from metarpg.assembler import assemble_patch
from metarpg.models import ActHypothesis, Claim, ClaimStatus, ProposedEffect
from metarpg.scenarios.greyfen import build


def _world():
    return build()


def test_assembles_ask_patch_from_validated_hypothesis():
    w = _world()
    hyp = ActHypothesis(
        act_kind="ask_about_topic",
        confidence=0.75,
        support_claims=[
            Claim("same_location", ("player", "mara"), ClaimStatus.ACCEPTED),
            Claim("can_speak_to", ("player", "mara"), ClaimStatus.ACCEPTED),
        ],
        intended_effects=[
            ProposedEffect("event", ("player_asked_mara_about_mine",), 0),
            ProposedEffect("rel_delta", ("mara", "player", "trust", 0.02), 1),
        ],
        target="mara",
        topic="mine",
    )
    patch = assemble_patch(hyp, w)
    assert any(e.kind == "event" for e in patch.effects)
    assert any(e.kind == "rel_delta" for e in patch.effects)


def test_filters_high_impact_effect_when_claims_weak():
    w = _world()
    hyp = ActHypothesis(
        act_kind="ask_about_topic",
        confidence=0.75,
        support_claims=[
            Claim("same_location", ("player", "mara"), ClaimStatus.UNKNOWN),
        ],
        intended_effects=[
            ProposedEffect("belief_delta", ("mara_knows_recent_entry", 0.10), 2),
        ],
        target="mara",
    )
    patch = assemble_patch(hyp, w)
    # belief_delta (impact 2) should be filtered because core claim is weak
    assert not any(e.kind == "belief_delta" for e in patch.effects)


def test_unknown_claim_downgrades_event_to_transient():
    w = _world()
    hyp = ActHypothesis(
        act_kind="ambiguous_social_act",
        confidence=0.40,
        support_claims=[
            Claim("same_location", ("player", "mara"), ClaimStatus.UNKNOWN),
        ],
        intended_effects=[
            ProposedEffect("event", ("player_spoke_unclearly_to_mara",), 0),
        ],
        target="mara",
    )
    patch = assemble_patch(hyp, w)
    # UNKNOWN core claim -> event downgraded to transient_event
    assert any(e.kind == "transient_event" for e in patch.effects)
    assert not any(e.kind == "event" for e in patch.effects)


def test_hard_fact_requires_accepted_claims():
    w = _world()
    hyp = ActHypothesis(
        act_kind="move_to_place",
        confidence=0.80,
        support_claims=[
            Claim("same_location", ("player", "mara"), ClaimStatus.INFERRED),
        ],
        intended_effects=[
            ProposedEffect("add_fact", ("at", ("player", "guard_post")), 3),
        ],
        target="guard_post",
    )
    patch = assemble_patch(hyp, w)
    # hard fact (impact 3) filtered because no ACCEPTED core claims
    assert not any(e.kind == "add_fact" for e in patch.effects)
