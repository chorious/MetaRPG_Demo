import pytest

from metarpg.agentic.transaction import Commitment, Operation, TurnTransaction
from metarpg.agentic.transaction_validator import validate_transaction
from metarpg.models import Fact, WorldState


def _make_world() -> WorldState:
    world = WorldState()
    world.facts = {
        Fact("at", ("player", "entrance_hall")),
        Fact("at", ("alen", "entrance_hall")),
        Fact("has", ("player", "torch")),
        Fact("has", ("player", "short_sword")),
        Fact("sealed", ("lower_vault_door",)),
    }
    world.locations = {"entrance_hall", "old_guardroom", "flooded_stair", "sealed_lower_door"}
    world.npcs = {"alen"}
    return world


def test_missing_item_rejected():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("extinguish_item", {"item": "lantern"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "missing_item" for i in result.issues)


def test_valid_item_accepted():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("extinguish_item", {"item": "torch"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "accepted"


def test_absent_entity_rejected():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("speak", {"entity": "ghost"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "absent_entity" for i in result.issues)


def test_present_entity_accepted():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("speak", {"entity": "alen"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "accepted"


def test_unknown_location_rejected():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("move_player", {"destination": "moon"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "unknown_location" for i in result.issues)


def test_known_location_accepted():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("move_player", {"destination": "old_guardroom"})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "accepted"


def test_hidden_truth_direct_reveal_rejected():
    world = _make_world()
    world.hidden_truths = {
        "h_relic": {"aliases": ["reliquary", "stolen relic"]},
    }
    tx = TurnTransaction(
        commitments=[Commitment("canon", "The stolen relic was moved below")],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "hidden_truth_direct_reveal" for i in result.issues)


def test_canon_downgraded_to_utterance_without_evidence():
    world = _make_world()
    tx = TurnTransaction(
        commitments=[Commitment("canon", "Player feels uneasy")],
    )
    result = validate_transaction(tx, world)
    assert result.status == "downgraded"
    assert result.transaction is not None
    assert result.transaction.commitments[0].level == "utterance"
    assert result.downgrades[0].original_commitment == "canon"
    assert result.downgrades[0].new_commitment == "utterance"


def test_reveal_downgraded_to_hint():
    world = _make_world()
    tx = TurnTransaction(
        commitments=[Commitment("reveal", "The door has three marks")],
    )
    result = validate_transaction(tx, world)
    assert result.status == "downgraded"
    assert result.transaction is not None
    assert result.transaction.commitments[0].level == "hint"


def test_new_item_downgraded_to_texture():
    world = _make_world()
    tx = TurnTransaction(
        commitments=[Commitment("new_item", "A mysterious ring appears")],
    )
    result = validate_transaction(tx, world)
    assert result.status == "downgraded"
    assert result.transaction is not None
    assert result.transaction.commitments[0].level == "texture"


def test_intra_turn_contradiction():
    world = _make_world()
    tx = TurnTransaction(
        operations=[
            Operation("move_player", {"destination": "old_guardroom"}),
            Operation("move_player", {"destination": "old_guardroom"}),
        ],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "intra_turn_contradiction" for i in result.issues)


def test_relation_delta_out_of_bounds():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("update_relation", {"dim": "trust", "delta": 2.0})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "relation_delta_out_of_bounds" for i in result.issues)


def test_belief_delta_out_of_bounds():
    world = _make_world()
    tx = TurnTransaction(
        operations=[Operation("update_belief", {"delta": -0.5})],
    )
    result = validate_transaction(tx, world)
    assert result.status == "rejected"
    assert any(i.type == "belief_delta_out_of_bounds" for i in result.issues)
