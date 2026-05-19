"""Tests for L2 repair loop (v0.7.3 Phase 3).

These are unit tests for render_repair.py and repair-aware checker logic.
Full integration tests require live Flash client.
"""
from __future__ import annotations

import pytest

from metarpg.agentic.render_repair import _build_repair_user_prompt
from metarpg.agentic.transaction import RenderBrief


class TestBuildRepairUserPrompt:
    def test_contains_all_sections(self):
        brief = RenderBrief(
            committed_events=["Player inspects the door."],
            visible_entities=["player"],
            absent_entities=["alen"],
            player_location="flooded_stair",
            allowed_hints=["hint_door_three_marks"],
        )
        prompt = _build_repair_user_prompt(
            original_prose="The door has three marks.",
            issues=["L2 semantic: hidden truth exposure"],
            semantic_judgments=[{"check": "hidden_truth_exposure", "verdict": "reject"}],
            render_brief=brief,
        )
        assert "Original Prose" in prompt
        assert "Issues to Fix" in prompt
        assert "Visible Entities" in prompt
        assert "Absent Entities" in prompt
        assert "Player Location" in prompt
        assert "flooded_stair" in prompt
        assert "alen" in prompt

    def test_empty_lists(self):
        brief = RenderBrief()
        prompt = _build_repair_user_prompt(
            original_prose="Test.",
            issues=[],
            semantic_judgments=[],
            render_brief=brief,
        )
        assert "Test." in prompt
        assert "None" in prompt
