"""Validator and forbidden-pattern tests."""
from __future__ import annotations

from metarpg.models import Effect, Fact, Patch, WorldState
from metarpg.rules import check_forbidden, validate_patch


def _world_with(*facts: Fact) -> WorldState:
    w = WorldState()
    for f in facts:
        w.facts.add(f)
    return w


def test_same_location_required_passes():
    w = _world_with(Fact("at", ("player", "tavern")), Fact("at", ("mara", "tavern")))
    p = Patch(intent="ask", requirements=["same_location(player,mara)"])
    vr = validate_patch(w, p)
    assert vr.ok, vr.reason


def test_same_location_required_fails():
    w = _world_with(Fact("at", ("player", "tavern")), Fact("at", ("mara", "guard_post")))
    p = Patch(intent="ask", requirements=["same_location(player,mara)"])
    vr = validate_patch(w, p)
    assert not vr.ok
    assert "not_same_location" in vr.reason


def test_accessible_sealed_without_path_fails():
    w = _world_with(Fact("sealed", ("old_mine",)))
    p = Patch(intent="enter", requirements=["accessible(old_mine)"])
    vr = validate_patch(w, p)
    assert not vr.ok
    assert "inaccessible" in vr.reason


def test_accessible_with_key_passes():
    w = _world_with(
        Fact("sealed", ("old_mine",)),
        Fact("holds_key", ("player", "old_mine")),
    )
    p = Patch(intent="enter", requirements=["accessible(old_mine)"])
    vr = validate_patch(w, p)
    assert vr.ok


def test_forbidden_alive_and_dead():
    w = _world_with(Fact("alive", ("iven",)), Fact("dead", ("iven",)))
    vr = check_forbidden(w)
    assert not vr.ok
    assert "alive_and_dead" in vr.reason


def test_forbidden_two_locations():
    w = _world_with(Fact("at", ("mara", "tavern")), Fact("at", ("mara", "guard_post")))
    vr = check_forbidden(w)
    assert not vr.ok
    assert "two_locations" in vr.reason


def test_forbidden_entry_without_access():
    w = _world_with(
        Fact("sealed", ("old_mine",)),
    )
    vr = check_forbidden(
        w,
        candidate_facts=[Fact("entered", ("mara", "old_mine", "day_minus_2"))],
    )
    assert not vr.ok
    assert "entry_without_access" in vr.reason


def test_entry_with_passage_path_passes():
    w = _world_with(Fact("sealed", ("old_mine",)))
    vr = check_forbidden(
        w,
        candidate_facts=[
            Fact("found_passage", ("mara", "old_mine")),
            Fact("entered", ("mara", "old_mine", "day_minus_2")),
        ],
    )
    assert vr.ok
