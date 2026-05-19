"""Targeted tests for absence_response (v0.7.2.1)."""
from __future__ import annotations

import pytest

from metarpg.agentic.reference_resolver import resolve_references
from metarpg.agentic.runner import _build_absence_response
from metarpg.agentic.seed_loader import WorldSeed
from metarpg.models import Fact, WorldState


def _make_seed() -> WorldSeed:
    return WorldSeed(
        locations={
            "entrance_hall": {"aliases": ["入口厅"]},
            "flooded_stair": {"aliases": ["积水阶梯"]},
        },
        entities={"alen": {"aliases": ["艾伦"]}, "player": {"aliases": []}},
        items={},
        active_hooks={},
        motifs={},
    )


# ---------------------------------------------------------------------------
# Test A — Direct world state construction
# ---------------------------------------------------------------------------


def test_resolver_marks_absent_entity_unavailable():
    """When alen is not in available_entities, ResolvedRef.available=False."""
    seed = _make_seed()
    intent = resolve_references(
        player_input="我问艾伦关于下层密室的事。",
        known_entities=list(seed.entities.keys()),
        known_items=[],
        known_locations=list(seed.locations.keys()),
        known_hooks=[],
        known_motifs=[],
        aliases_map={"alen": ["艾伦"], "player": []},
        available_entities=["player"],  # alen NOT available
        available_items=[],
        available_locations=[],
        available_hooks=[],
        available_motifs=[],
    )
    assert len(intent.targets) >= 1
    alen_ref = next((r for r in intent.targets if r.canonical_id == "alen"), None)
    assert alen_ref is not None
    assert alen_ref.available is False



def test_resolver_marks_present_entity_available():
    """When alen IS in available_entities, ResolvedRef.available=True."""
    seed = _make_seed()
    intent = resolve_references(
        player_input="我问艾伦关于下层密室的事。",
        known_entities=list(seed.entities.keys()),
        known_items=[],
        known_locations=list(seed.locations.keys()),
        known_hooks=[],
        known_motifs=[],
        aliases_map={"alen": ["艾伦"], "player": []},
        available_entities=["player", "alen"],
        available_items=[],
        available_locations=[],
        available_hooks=[],
        available_motifs=[],
    )
    alen_ref = next((r for r in intent.targets if r.canonical_id == "alen"), None)
    assert alen_ref is not None
    assert alen_ref.available is True


def test_build_absence_response_structure():
    """_build_absence_response produces correct transaction structure."""
    from metarpg.agentic.reference_resolver import ResolvedRef
    from metarpg.agentic.transaction import NarrativeFrame

    frame = NarrativeFrame(beat="social_pressure")
    absent_refs = [ResolvedRef("艾伦", "alen", "entity", 0.95, available=False)]
    tx = _build_absence_response("我问艾伦。", frame, absent_refs, "test_001")

    assert tx.id == "test_001"
    assert any(a.get("source") == "absence_response" for a in tx.assumptions)
    assert tx.operations[0].kind == "observe_reaction"
    assert "alen" in tx.operations[0].params.get("description", "")
    assert tx.commitments[0].level == "texture"


# ---------------------------------------------------------------------------
# Test B — Real movement sequence
# ---------------------------------------------------------------------------


def test_movement_changes_entity_availability():
    """After player moves away, alen is no longer in visible_entities."""
    from metarpg.agentic.committer import commit_transaction
    from metarpg.agentic.transaction import Operation, TurnTransaction

    world = WorldState(
        turn=1,
        locations={"entrance_hall", "flooded_stair"},
        npcs={"alen", "player"},
        facts={
            Fact("at", ("player", "entrance_hall")),
            Fact("at", ("alen", "entrance_hall")),
        },
    )

    # Move player to flooded_stair
    tx = TurnTransaction(
        player_input="我沿着积水阶梯往下走。",
        operations=[Operation("move_player", {"destination": "flooded_stair"})],
        commitments=[],
    )
    commit_transaction(world, tx)

    # Now build scene context as runner would
    player_loc = next(
        (f.args[1] for f in world.facts if f.predicate == "at" and f.args[0] == "player"),
        "",
    )
    assert player_loc == "flooded_stair"

    # Alen is still at entrance_hall, player is at flooded_stair
    alen_loc = next(
        (f.args[1] for f in world.facts if f.predicate == "at" and f.args[0] == "alen"),
        "",
    )
    assert alen_loc == "entrance_hall"
    assert alen_loc != player_loc

    # Resolve reference with scene-visible entities (only player at flooded_stair)
    seed = _make_seed()
    intent = resolve_references(
        player_input="我问艾伦关于下层密室的事。",
        known_entities=list(seed.entities.keys()),
        known_items=[],
        known_locations=list(seed.locations.keys()),
        known_hooks=[],
        known_motifs=[],
        aliases_map={"alen": ["艾伦"], "player": []},
        available_entities=["player"],  # alen NOT at player location
        available_items=[],
        available_locations=["flooded_stair", "entrance_hall"],
        available_hooks=[],
        available_motifs=[],
    )
    alen_ref = next((r for r in intent.targets if r.canonical_id == "alen"), None)
    assert alen_ref is not None
    assert alen_ref.available is False
