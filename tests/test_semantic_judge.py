"""Tests for semantic_judge.py — L2 semantic boundary checks.

These tests exercise the deterministic / no-LLM paths.
LLM-dependent paths are integration-tested in smoke tests.
"""
from __future__ import annotations

import pytest

from metarpg.agentic.semantic_judge import (
    SemanticJudgment,
    judge_hidden_truth_exposure,
    judge_hook_relevance,
    judge_render_claim_support,
)


class TestNoClientFallback:
    """When no LlmClient is provided, judges return permissive pass."""

    def test_hook_relevance_no_client(self):
        results = judge_hook_relevance(
            player_intent={"action_type": "inspect"},
            active_hooks=[{"id": "hook_1", "tension": "test"}],
            recent_events=[],
            client=None,
        )
        assert results == []

    def test_hidden_truth_no_client(self):
        result = judge_hidden_truth_exposure(
            text="The door is old.",
            hidden_truths=[{"id": "h_1", "statement": "secret"}],
            client=None,
        )
        assert result.verdict == "pass"
        assert result.category == "no_llm_available"

    def test_render_claim_no_client(self):
        result = judge_render_claim_support(
            prose="The ash smells bitter.",
            transaction_summary={},
            world_facts=[],
            client=None,
        )
        assert result.verdict == "pass"
        assert result.category == "no_llm_available"


class TestSemanticJudgmentSchema:
    def test_valid_verdicts(self):
        for v in ("pass", "downgrade", "reject"):
            j = SemanticJudgment(
                verdict=v, category="test", evidence="", suggested_downgrade=None, confidence=0.9
            )
            assert j.verdict == v
