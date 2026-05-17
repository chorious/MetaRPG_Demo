"""Tests for committer (Phase G)."""
from __future__ import annotations

from metarpg.agentic.committer import commit_turn
from metarpg.agentic.schemas import CandidatePatchEffect, Segment
from metarpg.models import Fact, WorldState


def _world_with_ale() -> WorldState:
    w = WorldState()
    w.facts.add(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("has", ("player", "ale")))
    return w


def test_commit_consume_item():
    w = _world_with_ale()
    patch = [CandidatePatchEffect(kind="consume_item", args={"item": "ale"})]
    segments = [Segment(id="s1", type="player_action", text="你喝光了酒。")]
    result = commit_turn(w, patch, segments)
    assert result["turn"] == 1
    assert "ale" in result["delta"]["items_consumed"]
    assert Fact("has", ("player", "ale")) not in w.facts


def test_commit_move():
    w = _world_with_ale()
    w.locations.add("guard_post")
    patch = [CandidatePatchEffect(kind="move", args={"entity": "player", "destination": "guard_post"})]
    segments = [Segment(id="s1", type="player_action", text="你走向守卫站。")]
    result = commit_turn(w, patch, segments)
    assert Fact("at", ("player", "guard_post")) in w.facts
    assert Fact("at", ("player", "tavern")) not in w.facts


def test_commit_acquire_item():
    w = _world_with_ale()
    patch = [CandidatePatchEffect(kind="acquire_item", args={"item": "dagger"})]
    segments = [Segment(id="s1", type="player_action", text="你拿起匕首。")]
    result = commit_turn(w, patch, segments)
    assert Fact("has", ("player", "dagger")) in w.facts
    assert "dagger" in result["delta"]["items_acquired"]


def test_commit_player_output():
    w = _world_with_ale()
    patch = []
    segments = [
        Segment(id="s1", type="player_action", text="你环顾四周。"),
        Segment(id="s2", type="description", text="酒馆里很安静。"),
    ]
    result = commit_turn(w, patch, segments)
    assert "你环顾四周。" in result["player_output"]
    assert "酒馆里很安静。" in result["player_output"]
