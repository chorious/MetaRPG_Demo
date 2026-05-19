from pathlib import Path

import pytest

from metarpg.agentic.committer import commit_transaction, commit_turn
from metarpg.agentic.schemas import CandidatePatchEffect
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.transaction import Commitment, Operation, TurnTransaction
from metarpg.agentic.world_graph import world_from_seed
from metarpg.models import Fact, WorldState

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")


# ---------------------------------------------------------------------------
# world_from_seed
# ---------------------------------------------------------------------------


def test_world_from_seed_populates_facts():
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)
    assert any(f.predicate == "at" and f.args == ("player", "entrance_hall") for f in world.facts)
    assert any(f.predicate == "has" and f.args == ("player", "torch") for f in world.facts)


def test_world_from_seed_entities():
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)
    assert "alen" in world.npcs
    assert "player" not in world.npcs  # player is special


# ---------------------------------------------------------------------------
# commit_transaction
# ---------------------------------------------------------------------------


def test_commit_event():
    world = WorldState()
    tx = TurnTransaction(
        operations=[Operation("add_event", {"summary": "Player inspects ash"})],
    )
    result = commit_transaction(world, tx)
    assert len(world.events) == 1
    assert world.events[0]["summary"] == "Player inspects ash"
    assert result["turn"] == 1


def test_commit_utterance_not_canon():
    world = WorldState()
    tx = TurnTransaction(
        commitments=[Commitment("utterance", "Alen says 'I do not know'")],
    )
    commit_transaction(world, tx)
    assert len(world.utterances) == 1
    assert not any("Alen says" in str(f) for f in world.facts)


def test_commit_texture_not_canon():
    world = WorldState()
    tx = TurnTransaction(
        commitments=[Commitment("texture", "The air smells of ash")],
    )
    commit_transaction(world, tx)
    assert len(getattr(world, "events", [])) == 0
    assert len(getattr(world, "utterances", [])) == 0
    assert not any("smells of ash" in str(f) for f in world.facts)


def test_commit_relation_delta():
    world = WorldState()
    world.facts.add(Fact("at", ("player", "entrance_hall")))
    world.facts.add(Fact("at", ("alen", "entrance_hall")))
    tx = TurnTransaction(
        operations=[
            Operation(
                "update_relation",
                {"entity_a": "player", "entity_b": "alen", "dim": "trust", "delta": 0.2},
            )
        ],
    )
    commit_transaction(world, tx)
    rel = world.get_relation("player", "alen")
    assert rel is not None
    assert rel.get("trust") == pytest.approx(0.2)


def test_commit_belief_delta():
    world = WorldState()
    from metarpg.models import Belief

    world.beliefs["b_test"] = Belief("b_test", "test belief", 0.5)
    tx = TurnTransaction(
        operations=[Operation("update_belief", {"belief_id": "b_test", "delta": 0.1})],
    )
    commit_transaction(world, tx)
    assert world.beliefs["b_test"].prob == pytest.approx(0.6)


def test_commit_move_player():
    world = WorldState()
    world.facts.add(Fact("at", ("player", "entrance_hall")))
    tx = TurnTransaction(
        operations=[Operation("move_player", {"destination": "old_guardroom"})],
    )
    commit_transaction(world, tx)
    assert any(
        f.predicate == "at" and f.args == ("player", "old_guardroom") for f in world.facts
    )


def test_commit_mark_hook_status():
    world = WorldState()
    tx = TurnTransaction(
        operations=[Operation("mark_hook_status", {"hook_id": "hook_test", "status": "resolved"})],
    )
    commit_transaction(world, tx)
    assert world._hook_status["hook_test"] == "resolved"


# ---------------------------------------------------------------------------
# Legacy commit_turn still works
# ---------------------------------------------------------------------------


def test_legacy_commit_turn_untouched():
    world = WorldState()
    world.facts.add(Fact("at", ("player", "entrance_hall")))
    patch = [
        CandidatePatchEffect("move", {"entity": "player", "destination": "old_guardroom"})
    ]
    result = commit_turn(world, patch, [])
    assert result["turn"] == 1
    assert any(
        f.predicate == "at" and f.args == ("player", "old_guardroom") for f in world.facts
    )
