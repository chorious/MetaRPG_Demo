"""Tests for agentic story packet builder (Phase B)."""
from __future__ import annotations

from metarpg.models import Fact, WorldState
from metarpg.agentic.story_packet import build_story_packet


def _greyfen_world() -> WorldState:
    w = WorldState()
    w.npcs = {"mara", "rusk", "iven"}
    w.locations = {"tavern", "guard_post", "old_mine", "old_mine_gate", "mara_cellar"}
    w.roles = {"mara": {"tavernkeeper"}, "rusk": {"guard"}, "iven": {"merchant"}}
    w.place_services = {
        "tavern": {"drink", "talk", "rest"},
        "guard_post": {"talk", "report"},
        "old_mine_gate": {"exit"},
    }
    # Player at tavern
    w.facts.add(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("at", ("mara", "tavern")))
    w.facts.add(Fact("at", ("rusk", "guard_post")))
    w.facts.add(Fact("has", ("player", "ale")))
    w.facts.add(Fact("old_mine_is_sealed", ("true",)))
    w.facts.add(Fact("secret_mine_entrance_exists", ("true",)))
    return w


def test_story_packet_has_location():
    w = _greyfen_world()
    pkt = build_story_packet(w)
    assert pkt["scene"]["location"] == "tavern"


def test_story_packet_has_nearby_npcs():
    w = _greyfen_world()
    pkt = build_story_packet(w)
    assert "mara" in pkt["scene"]["visible_entities"]
    assert "rusk" not in pkt["scene"]["visible_entities"]


def test_story_packet_has_inventory():
    w = _greyfen_world()
    pkt = build_story_packet(w)
    assert "ale" in pkt["player_context"]["inventory_or_handheld"]


def test_story_packet_does_not_expose_hidden_facts():
    w = _greyfen_world()
    pkt = build_story_packet(w)
    visible = str(pkt["player_context"])
    scene = str(pkt["scene"])
    assert "secret_mine_entrance" not in visible
    assert "secret_mine_entrance" not in scene
    # But hidden truth exists in auditor_only
    hidden_aliases = [h.get("alias", "") for h in pkt["auditor_only"]["hidden_truths"]]
    assert "secret_mine_entrance_exists" in hidden_aliases


def test_story_packet_includes_recent_events():
    w = _greyfen_world()
    w.facts.add(Fact("ordered", ("player", "ale", "mara")))
    pkt = build_story_packet(w)
    recent = pkt["player_context"]["recent_events"]
    assert any("ordered(player,ale,mara)" in e for e in recent)


def test_story_packet_forbidden_has_absent_entities():
    w = _greyfen_world()
    pkt = build_story_packet(w)
    assert "rusk" in pkt["forbidden"]["entities_not_present"]
