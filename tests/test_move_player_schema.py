"""Tests for move_player schema hardening (v0.7.2.1)."""
from __future__ import annotations

import pytest

from metarpg.agentic.committer import commit_transaction
from metarpg.agentic.director_agent import _parse_transaction, _validate_structure
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    TurnTransaction,
)
from metarpg.agentic.transaction_validator import validate_transaction
from metarpg.models import Fact, WorldState


def _make_world(player_loc: str = "entrance_hall") -> WorldState:
    w = WorldState(
        turn=1,
        locations={"entrance_hall", "old_guardroom", "flooded_stair", "sealed_lower_door"},
        npcs={"alen", "player"},
        facts={
            Fact("at", ("player", player_loc)),
            Fact("at", ("alen", "entrance_hall")),
        },
    )
    return w


def test_move_player_target_normalized_to_destination():
    """Director output with target=flooded_stair must be normalized to destination."""
    raw = {
        "player_input": "我沿着积水阶梯往下走。",
        "operations": [
            {"kind": "move_player", "params": {"target": "flooded_stair", "description": "desc"}}
        ],
        "commitments": [],
        "assumptions": [],
    }
    tx = _parse_transaction(raw)
    op = tx.operations[0]
    assert op.kind == "move_player"
    assert "destination" in op.params
    assert op.params["destination"] == "flooded_stair"
    assert "target" not in op.params


def test_move_player_target_location_normalized_to_destination():
    """Legacy target_location param must still be normalized."""
    raw = {
        "player_input": "Go to flooded stair",
        "operations": [
            {"kind": "move_player", "params": {"target_location": "flooded_stair"}}
        ],
        "commitments": [],
        "assumptions": [],
    }
    tx = _parse_transaction(raw)
    assert tx.operations[0].params["destination"] == "flooded_stair"


def test_move_player_missing_destination_hard_fails():
    """Validator must reject move_player without destination."""
    tx = TurnTransaction(
        player_input="move",
        operations=[Operation("move_player", {"description": "no dest"})],
        commitments=[],
    )
    world = _make_world()
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(iss.type == "missing_destination" for iss in result.issues)


def test_move_player_unknown_location_hard_fails():
    """Validator must reject move_player to non-existent location."""
    tx = TurnTransaction(
        player_input="move",
        operations=[Operation("move_player", {"destination": "moon"})],
        commitments=[],
    )
    world = _make_world()
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(iss.type == "unknown_location" for iss in result.issues)


def test_move_player_commit_changes_player_location():
    """Committer must update player location fact."""
    world = _make_world(player_loc="entrance_hall")
    tx = TurnTransaction(
        player_input="move",
        operations=[Operation("move_player", {"destination": "flooded_stair"})],
        commitments=[],
    )
    result = commit_transaction(world, tx)
    assert result["turn"] == 2  # commit_transaction increments turn
    at_facts = [f for f in world.facts if f.predicate == "at" and f.args[0] == "player"]
    assert len(at_facts) == 1
    assert at_facts[0].args[1] == "flooded_stair"


def test_move_player_commit_raises_on_missing_destination():
    """Committer must raise ValueError if move_player lacks destination."""
    world = _make_world()
    tx = TurnTransaction(
        player_input="move",
        operations=[Operation("move_player", {"target": "flooded_stair"})],
        commitments=[],
    )
    with pytest.raises(ValueError, match="move_player missing destination"):
        commit_transaction(world, tx)


def test_move_player_structure_validation_raises():
    """Director _validate_structure must raise if move_player lacks destination."""
    frame = NarrativeFrame(
        allowed_commitment_levels=["canon"],
        forbidden_moves=[],
        canonical_id_whitelist={
            "reachable_location_ids": ["flooded_stair"],
            "active_hook_ids": [],
        },
    )
    # If we bypass normalization and feed a tx without destination:
    tx_bad = TurnTransaction(
        player_input="move",
        operations=[Operation("move_player", {})],
        commitments=[],
    )
    with pytest.raises(ValueError, match="missing destination"):
        _validate_structure(tx_bad, frame)
