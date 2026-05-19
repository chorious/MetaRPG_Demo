"""Tests for Intent Fulfillment Judge (v0.7.4 Phase 2)."""
from __future__ import annotations

import pytest

from metarpg.agentic.semantic_judge import (
    SemanticJudgment,
    judge_intent_fulfillment,
)


class _MockJudgeClient:
    """Mock LlmClient that returns a preset response."""

    def __init__(self, response: dict) -> None:
        self.response = response

    def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        return self.response


class TestNoClientFallback:
    def test_intent_fulfillment_no_client(self):
        result = judge_intent_fulfillment(
            player_input="我搜索旧卫兵室。",
            resolved_intent={"action_type": "inspect", "targets": ["old_guardroom"]},
            prose="你蹲在密封的下层门前...",
            transaction_summary={},
            client=None,
        )
        assert result.verdict == "pass"
        assert result.category == "no_llm_available"


class TestIntentFulfilled:
    def test_passes_correct_action_and_target(self):
        mock_response = {
            "verdict": "pass",
            "category": "intent_fulfilled",
            "evidence": "prose describes searching the guardroom",
            "confidence": 0.92,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我搜索旧卫兵室。",
            resolved_intent={"action_type": "inspect", "targets": ["old_guardroom"]},
            prose="旧警卫室里积着厚厚一层灰...",
            transaction_summary={"operations": ["inspect"]},
            client=client,
        )
        assert result.verdict == "pass"
        assert result.category == "intent_fulfilled"


class TestWrongTarget:
    def test_rejects_stale_door_prose_for_guardroom_search(self):
        """Turn 5 regression: searching guardroom but prose writes pushing door."""
        mock_response = {
            "verdict": "reject",
            "category": "wrong_target",
            "evidence": "prose describes pushing the sealed lower door, not searching old_guardroom",
            "confidence": 0.95,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我搜索旧卫兵室。",
            resolved_intent={"action_type": "inspect", "targets": ["old_guardroom"]},
            prose="你蹲在密封的下层门前...发力...门纹丝不动...",
            transaction_summary={"operations": ["inner_monologue"]},
            client=client,
        )
        assert result.verdict == "reject"
        assert result.category == "wrong_target"


class TestStaleContext:
    def test_rejects_continuing_previous_turn(self):
        mock_response = {
            "verdict": "reject",
            "category": "stale_context",
            "evidence": "prose continues describing the door from previous turn instead of current action",
            "confidence": 0.88,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我回到入口厅。",
            resolved_intent={"action_type": "move", "targets": ["entrance_hall"]},
            prose="门板上的三道划痕依然清晰可见...",
            transaction_summary={"operations": ["move_player"]},
            client=client,
        )
        assert result.verdict == "reject"
        assert result.category == "stale_context"


class TestAbsenceResponse:
    def test_passes_absence_response(self):
        mock_response = {
            "verdict": "pass",
            "category": "intent_fulfilled",
            "evidence": "prose correctly notes target is absent",
            "confidence": 0.90,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我问艾伦关于下层密室的事。",
            resolved_intent={"action_type": "ask", "targets": ["alen"]},
            prose="水声沉寂...没人在这里。只有水声...",
            transaction_summary={"operations": ["inner_monologue"]},
            client=client,
        )
        assert result.verdict == "pass"


class TestDeterministicMovement:
    def test_passes_deterministic_movement(self):
        mock_response = {
            "verdict": "pass",
            "category": "intent_fulfilled",
            "evidence": "prose describes movement to destination",
            "confidence": 0.91,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我回到入口厅。",
            resolved_intent={"action_type": "move", "targets": ["entrance_hall"]},
            prose="你沿着来时的通道走回入口厅...",
            transaction_summary={"operations": ["move_player"]},
            client=client,
        )
        assert result.verdict == "pass"


class TestMissingRefusal:
    def test_rejects_when_unreachable_target_treated_as_present(self):
        mock_response = {
            "verdict": "reject",
            "category": "missing_refusal",
            "evidence": "prose acts as if player successfully reached the sealed door, but it was unreachable",
            "confidence": 0.87,
        }
        client = _MockJudgeClient(mock_response)
        result = judge_intent_fulfillment(
            player_input="我回到封闭下层门。",
            resolved_intent={"action_type": "move", "targets": ["sealed_lower_door"]},
            prose="你走到下层门前，仔细检查封印...",
            transaction_summary={"operations": ["inner_monologue"]},
            client=client,
        )
        assert result.verdict == "reject"
        assert result.category == "missing_refusal"
