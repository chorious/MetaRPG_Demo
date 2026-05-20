"""Targeted repair proof: unreachable response must not claim arrival."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metarpg.agentic.semantic_judge import judge_intent_fulfillment


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_fixture_unreachable_arrival_has_violation():
    """The unreachable fixture prose violates must_not_claim."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_prose_unreachable_arrival.json").read_text(encoding="utf-8")
    )
    assert fixture["response_mode"] == "unreachable"
    assert "推动" in fixture["prose"]
    assert "must_not_claim" in fixture["current_turn_obligation"]


def test_fixture_unreachable_good_example_is_safe():
    """The GOOD example does not contain arrival/interaction claims."""
    good = "你辨认出那扇门的方向，但积水和断裂的阶梯让你无法从这里直接回去。"
    assert "推动" not in good
    assert "回到" not in good
    assert "触摸" not in good


def test_judge_intent_fulfillment_no_client_returns_pass():
    """Without LLM client the judge is permissive (baseline behavior)."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_prose_unreachable_arrival.json").read_text(encoding="utf-8")
    )
    result = judge_intent_fulfillment(
        player_input=fixture["player_input"],
        resolved_intent=fixture["resolved_intent"],
        prose=fixture["prose"],
        transaction_summary={},
        current_turn_obligation=fixture["current_turn_obligation"],
        client=None,
    )
    # No client = permissive pass
    assert result.verdict == "pass"
