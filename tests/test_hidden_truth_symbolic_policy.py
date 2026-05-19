"""Tests for hidden truth symbolic hint policy (v0.7.3 Phase 4).

These tests exercise the deterministic / mocked-LLM paths.
The actual symbolic judgment quality depends on the LLM following the
injected risk patterns and safe_hint_boundary.
"""
from __future__ import annotations

import json

import pytest

from metarpg.agentic.semantic_judge import judge_hidden_truth_exposure


class _CapturingMockClient:
    """Mock LlmClient that returns a preset response and captures messages."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.captured_messages: list[dict] | None = None

    def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        self.captured_messages = messages
        return self.response


class TestSymbolicRiskPatternsInPrompt:
    """Verify symbolic_risk_patterns and safe_hint_boundary reach the LLM prompt."""

    def test_payload_includes_symbolic_risk_patterns(self):
        mock_response = {
            "verdict": "pass",
            "category": "test",
            "evidence": "test",
            "confidence": 0.9,
        }
        client = _CapturingMockClient(mock_response)
        hidden_truth = {
            "id": "h_test",
            "statement": "A secret mechanism.",
            "symbolic_risk_patterns": [
                {"concepts": ["three", "door", "response"]},
            ],
        }
        judge_hidden_truth_exposure(
            text="The door is old.",
            hidden_truths=[hidden_truth],
            client=client,
        )
        assert client.captured_messages is not None
        user_msg = client.captured_messages[1]["content"]
        payload = json.loads(user_msg)
        ht = payload["hidden_truths"][0]
        assert "symbolic_risk_patterns" in ht
        assert ht["symbolic_risk_patterns"][0]["concepts"] == ["three", "door", "response"]

    def test_payload_includes_safe_hint_boundary(self):
        mock_response = {
            "verdict": "pass",
            "category": "test",
            "evidence": "test",
            "confidence": 0.9,
        }
        client = _CapturingMockClient(mock_response)
        hidden_truth = {
            "id": "h_test",
            "statement": "A secret mechanism.",
            "safe_hint_boundary": {
                "allowed": ["old scratches"],
                "disallowed": ["exact count"],
            },
        }
        judge_hidden_truth_exposure(
            text="The metal has old scratches.",
            hidden_truths=[hidden_truth],
            client=client,
        )
        assert client.captured_messages is not None
        user_msg = client.captured_messages[1]["content"]
        payload = json.loads(user_msg)
        ht = payload["hidden_truths"][0]
        assert "safe_hint_boundary" in ht
        assert ht["safe_hint_boundary"]["allowed"] == ["old scratches"]


class TestSymbolicVerdicts:
    """Verdict behavior with mocked LLM responses."""

    def test_three_alone_not_flagged(self):
        """Isolated 'three' should not be flagged when LLM says pass."""
        mock_response = {
            "verdict": "pass",
            "category": "isolated_number",
            "evidence": "'three' alone is not a bridge",
            "confidence": 0.85,
        }
        client = _CapturingMockClient(mock_response)
        hidden_truth = {
            "id": "h_bell_sequence_opens_door",
            "statement": "The lower vault door responds to a three-note bell sequence.",
            "symbolic_risk_patterns": [
                {"concepts": ["three", "door", "response"]},
            ],
        }
        result = judge_hidden_truth_exposure(
            text="You see three stones.",
            hidden_truths=[hidden_truth],
            client=client,
        )
        assert result.verdict == "pass"

    def test_three_door_response_flagged(self):
        """Combination of three + door + response should trigger reject."""
        mock_response = {
            "verdict": "reject",
            "category": "symbolic_bridge",
            "evidence": "'three marks waiting for a response on the door' bridges to hidden truth",
            "confidence": 0.92,
        }
        client = _CapturingMockClient(mock_response)
        hidden_truth = {
            "id": "h_bell_sequence_opens_door",
            "statement": "The lower vault door responds to a three-note bell sequence.",
            "symbolic_risk_patterns": [
                {"concepts": ["three", "door", "response"]},
            ],
        }
        result = judge_hidden_truth_exposure(
            text="The door has three marks waiting for a response.",
            hidden_truths=[hidden_truth],
            client=client,
        )
        assert result.verdict == "reject"

    def test_safe_wear_hint_allowed(self):
        """Safe boundary hints like 'old scratches' should pass."""
        mock_response = {
            "verdict": "pass",
            "category": "safe_hint",
            "evidence": "'old scratches' is in safe_hint_boundary.allowed",
            "confidence": 0.88,
        }
        client = _CapturingMockClient(mock_response)
        hidden_truth = {
            "id": "h_bell_sequence_opens_door",
            "statement": "The lower vault door responds to a three-note bell sequence.",
            "safe_hint_boundary": {
                "allowed": ["old scratches", "uneven wear", "cold metal vibration"],
                "disallowed": ["exact count of three linked to mechanism"],
            },
        }
        result = judge_hidden_truth_exposure(
            text="The metal shows old scratches and uneven wear.",
            hidden_truths=[hidden_truth],
            client=client,
        )
        assert result.verdict == "pass"


class TestRevealPolicyPassthrough:
    def test_reveal_policy_reaches_prompt(self):
        mock_response = {
            "verdict": "pass",
            "category": "test",
            "evidence": "test",
            "confidence": 0.9,
        }
        client = _CapturingMockClient(mock_response)
        judge_hidden_truth_exposure(
            text="Something.",
            hidden_truths=[{"id": "h_1", "statement": "secret"}],
            reveal_policy="hint_first",
            client=client,
        )
        assert client.captured_messages is not None
        user_msg = client.captured_messages[1]["content"]
        payload = json.loads(user_msg)
        assert payload["reveal_policy"] == "hint_first"
