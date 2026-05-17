"""Claim validation tests."""
from __future__ import annotations

from metarpg.claims import validate_claim
from metarpg.models import ClaimStatus, Fact
from metarpg.scenarios.greyfen import build


def _world():
    return build()


def test_same_location_accepted_from_facts():
    w = _world()
    c = validate_claim(w, "same_location", ("player", "mara"))
    assert c.status == ClaimStatus.ACCEPTED


def test_same_location_rejected_from_facts():
    w = _world()
    c = validate_claim(w, "same_location", ("player", "rusk"))
    assert c.status == ClaimStatus.REJECTED


def test_can_speak_to_accepted():
    w = _world()
    c = validate_claim(w, "can_speak_to", ("player", "mara"))
    assert c.status == ClaimStatus.ACCEPTED


def test_role_supports_inferred_from_tags():
    w = _world()
    c = validate_claim(w, "role_supports", ("mara", "bartender_service"))
    assert c.status == ClaimStatus.ACCEPTED


def test_role_supports_unknown_for_missing():
    w = _world()
    c = validate_claim(w, "role_supports", ("mara", "blacksmith"))
    assert c.status == ClaimStatus.UNKNOWN


def test_place_supports_inferred_from_tags():
    w = _world()
    c = validate_claim(w, "place_supports", ("tavern", "drink_service"))
    assert c.status == ClaimStatus.ACCEPTED


def test_item_plausible_probable_from_tags():
    w = _world()
    c = validate_claim(w, "item_plausible", ("ale", "tavern"))
    assert c.status == ClaimStatus.ACCEPTED


def test_social_tone_inferred_from_cues():
    w = _world()
    c = validate_claim(w, "social_tone", ("怎么回事，你们甚至没有酒", "irritated"))
    assert c.status == ClaimStatus.INFERRED


def test_topic_plausible_for_place_inferred():
    w = _world()
    c = validate_claim(w, "topic_plausible_for_place", ("mine", "tavern"))
    assert c.status == ClaimStatus.ACCEPTED


def test_not_contradicts_locked_fact_accepted():
    w = _world()
    c = validate_claim(w, "not_contradicts_locked_fact", ("the mine is sealed",))
    assert c.status == ClaimStatus.ACCEPTED
