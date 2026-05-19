"""3-turn MVP smoke test for v0.7.0 transaction-first pipeline.

Uses monkey-patched Director and Renderer so the test is deterministic
and does not require live LLM endpoints.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from metarpg.agentic.feasibility import FeasibilityReport
from metarpg.agentic.runner import run_agentic_turn_v070
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    TurnTransaction,
)
from metarpg.agentic.world_graph import world_from_seed

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")


def _mock_director_turn1(player_input, narrative_frame, story_packet, client, max_retries=1):
    return TurnTransaction(
        player_input=player_input,
        narrative_frame=narrative_frame,
        operations=[
            Operation("inspect", {"target": "black_ash"}),
            Operation("add_event", {"summary": "Player inspects black ash on threshold"}),
        ],
        commitments=[
            Commitment("event", "Player inspects black ash", operation_index=1),
            Commitment("hint", "The ash smells of old magic", operation_index=0),
            Commitment("affordance", "Compare ash with other samples", operation_index=0),
        ],
    )


def _mock_director_turn2(player_input, narrative_frame, story_packet, client, max_retries=1):
    return TurnTransaction(
        player_input=player_input,
        narrative_frame=narrative_frame,
        operations=[
            Operation("speak", {"entity": "alen", "text": "I do not know what the ash is."}),
            Operation("add_event", {"summary": "Alen responds evasively about the ash"}),
        ],
        commitments=[
            Commitment("utterance", "Alen says 'I do not know'", operation_index=0),
            Commitment("belief_evidence", "Alen seems nervous", operation_index=0),
        ],
    )


def _mock_director_turn3(player_input, narrative_frame, story_packet, client, max_retries=1):
    return TurnTransaction(
        player_input=player_input,
        narrative_frame=narrative_frame,
        operations=[
            Operation("move_player", {"destination": "sealed_lower_door"}),
            Operation("inspect", {"target": "sealed_lower_door"}),
            Operation("add_event", {"summary": "Player approaches the sealed lower door"}),
        ],
        commitments=[
            Commitment("event", "Player approaches lower door", operation_index=2),
            Commitment("hint", "Three marks are carved above the door", operation_index=1),
        ],
    )


def _mock_renderer(render_brief, story_packet, client):
    return "门槛上的黑灰在火光下泛着细密的颗粒感。"


def _mock_feas_turn1(*args, **kwargs):
    return FeasibilityReport(
        stated_action="inspect threshold ash",
        stated_targets=["black_ash"],
        stated_props=[],
        world_response_kind="accept",
    )


def _mock_feas_turn2(*args, **kwargs):
    return FeasibilityReport(
        stated_action="ask alen about ash",
        stated_targets=["alen"],
        stated_props=["ash"],
        world_response_kind="accept",
    )


def _mock_feas_turn3(*args, **kwargs):
    return FeasibilityReport(
        stated_action="approach lower vault door",
        stated_targets=["sealed_lower_door"],
        stated_props=[],
        world_response_kind="accept",
    )


# ---------------------------------------------------------------------------
# 3-turn MVP
# ---------------------------------------------------------------------------


def test_v070_mvp_three_turns():
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)

    turns = [
        ("我检查门槛上的黑灰。", _mock_feas_turn1, _mock_director_turn1),
        ("我问艾伦这灰是怎么回事。", _mock_feas_turn2, _mock_director_turn2),
        ("我去看那扇封闭的下层门。", _mock_feas_turn3, _mock_director_turn3),
    ]

    results = []
    for idx, (player_input, feas_fn, director_fn) in enumerate(turns, start=1):
        with (
            patch("metarpg.agentic.runner.run_feasibility", side_effect=feas_fn),
            patch("metarpg.agentic.runner.run_director", side_effect=director_fn),
            patch("metarpg.agentic.runner.run_renderer", side_effect=_mock_renderer),
        ):
            result = run_agentic_turn_v070(
                world=world,
                player_input=player_input,
                turn_index=idx,
                run_id="mvp_smoke",
                seed=seed,
            )
            results.append(result)

    # Turn 1 assertions
    r1 = results[0]
    assert r1["narrative_frame"].beat == "inspection"
    assert r1["validation"].status in ("accepted", "downgraded")
    assert r1["player_output"]
    assert r1["post_render"]["status"] == "pass"
    assert len(world.events) >= 1

    # Turn 2 assertions
    r2 = results[1]
    assert r2["narrative_frame"].beat == "social_pressure"
    assert r2["validation"].status in ("accepted", "downgraded")
    assert len(world.utterances) >= 1

    # Turn 3 assertions
    r3 = results[2]
    # "去看" triggers inspect -> inspection beat; the move to door happens via operation
    assert r3["narrative_frame"].beat in ("inspection", "threshold_crossing", "arrival")
    assert any(
        f.predicate == "at" and f.args == ("player", "sealed_lower_door")
        for f in world.facts
    )

    # Global: 3 turns committed, no errors
    assert all(r["error"] is None for r in results)
    assert all(r["committed"] for r in results)


def _mock_feas_generic(*args, **kwargs):
    return FeasibilityReport(
        stated_action="use item",
        stated_targets=[],
        stated_props=["nonexistent_item"],
        world_response_kind="accept",
    )


def test_v070_validation_rejection_fallback():
    """If Director produces an invalid transaction, fallback is committed."""
    seed = load_seed(SEED_PATH)
    world = world_from_seed(seed)

    def _bad_director(*args, **kwargs):
        return TurnTransaction(
            player_input="test",
            operations=[
                Operation("consume_item", {"item": "nonexistent_item_12345"}),
            ],
            commitments=[],
        )

    with (
        patch("metarpg.agentic.runner.run_feasibility", side_effect=_mock_feas_generic),
        patch("metarpg.agentic.runner.run_director", side_effect=_bad_director),
        patch("metarpg.agentic.runner.run_renderer", side_effect=_mock_renderer),
    ):
        result = run_agentic_turn_v070(
            world=world,
            player_input="我使用不存在的物品。",
            turn_index=1,
            run_id="fallback_smoke",
            seed=seed,
        )

    assert result["validation"].status == "rejected"
    assert result["committed"] is True  # fallback committed
    assert "fallback" in str(result["transaction"].assumptions)
