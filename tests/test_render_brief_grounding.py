"""Tests for RenderBrief grounding and NPC spatial consistency (v0.7.3 Phase 2)."""
from __future__ import annotations

import pytest

from metarpg.agentic.render_brief import _get_absent_entities, _get_player_location, _get_visible_entities
from metarpg.agentic.transaction import NarrativeFrame, RenderBrief
from metarpg.models import Fact, WorldState


class TestGetPlayerLocation:
    def test_from_facts(self):
        world = WorldState()
        world.facts.add(Fact("at", ("player", "entrance_hall")))
        assert _get_player_location(world) == "entrance_hall"

    def test_empty(self):
        world = WorldState()
        assert _get_player_location(world) == ""


class TestGetVisibleEntities:
    def test_same_location(self):
        world = WorldState()
        world.facts.add(Fact("at", ("player", "entrance_hall")))
        world.facts.add(Fact("at", ("alen", "entrance_hall")))
        visible = _get_visible_entities(world, "entrance_hall")
        assert "alen" in visible
        assert "player" not in visible

    def test_different_location(self):
        world = WorldState()
        world.facts.add(Fact("at", ("player", "flooded_stair")))
        world.facts.add(Fact("at", ("alen", "entrance_hall")))
        visible = _get_visible_entities(world, "flooded_stair")
        assert "alen" not in visible

    def test_empty_location(self):
        world = WorldState()
        world.facts.add(Fact("at", ("alen", "entrance_hall")))
        visible = _get_visible_entities(world, "")
        assert visible == []


class TestGetAbsentEntities:
    def test_alen_absent(self):
        world = WorldState()
        world.npcs = {"alen", "guard_captain"}
        visible = ["alen"]
        absent = _get_absent_entities(world, visible)
        assert "guard_captain" in absent
        assert "alen" not in absent

    def test_all_present(self):
        world = WorldState()
        world.npcs = {"alen"}
        absent = _get_absent_entities(world, ["alen"])
        assert absent == []


class TestRenderBriefGrounding:
    def test_fields_populated(self):
        from metarpg.agentic.render_brief import build_render_brief
        from metarpg.agentic.transaction import TurnTransaction

        world = WorldState()
        world.facts.add(Fact("at", ("player", "entrance_hall")))
        world.facts.add(Fact("at", ("alen", "entrance_hall")))
        world.npcs = {"alen", "mysterious_stranger"}

        tx = TurnTransaction()
        frame = NarrativeFrame()
        brief = build_render_brief(tx, frame, world)

        assert brief.player_location == "entrance_hall"
        assert "alen" in brief.visible_entities
        assert "mysterious_stranger" in brief.absent_entities
