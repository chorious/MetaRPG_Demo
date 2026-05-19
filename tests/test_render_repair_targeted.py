"""Targeted proof tests for the render repair loop (v0.7.4 Phase 5)."""
from __future__ import annotations

import pytest

from metarpg.agentic.post_render_checker import check_rendered_prose
from metarpg.agentic.render_repair import run_render_repair
from metarpg.agentic.transaction import Commitment, Operation, RenderBrief, TurnTransaction
from metarpg.models import WorldState


class _MockFlashClient:
    """Mock Flash client that returns a preset repair result."""

    def __init__(self, repaired_prose: str):
        self.repaired_prose = repaired_prose

    def chat(self, messages: list[dict], temperature: float = 0.5) -> str:
        return self.repaired_prose


class _MockLocalClient:
    """Mock local vLLM that always passes L2 checks."""

    def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        return {
            "verdict": "pass",
            "category": "intent_fulfilled",
            "evidence": "mock pass",
            "confidence": 0.95,
        }


class _MockLocalClientHiddenTruthFail:
    """Mock local vLLM that rejects hidden truth exposure."""

    def __init__(self, reject_on: str = "hidden_truth"):
        self.reject_on = reject_on
        self.call_count = 0

    def chat_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        self.call_count += 1
        # Always reject (simulating repair impossible)
        return {
            "verdict": "reject",
            "category": "symbolic_bridge",
            "evidence": "mock persistent hidden truth leak",
            "confidence": 0.95,
        }


def _make_brief(**overrides) -> RenderBrief:
    defaults = {
        "committed_events": ["Player searched old guardroom."],
        "visible_entities": ["player"],
        "absent_entities": ["alen"],
        "player_location": "entrance_hall",
        "allowed_hints": [],
        "current_turn_obligation": {
            "player_input": "我搜索旧卫兵室。",
            "action_type": "inspect",
            "target_ids": ["old_guardroom"],
            "source": "director",
            "response_mode": "normal",
        },
    }
    defaults.update(overrides)
    return RenderBrief(**defaults)


def _make_tx() -> TurnTransaction:
    return TurnTransaction(
        player_input="我搜索旧卫兵室。",
        player_intent={"action_type": "inspect", "targets": ["old_guardroom"]},
        operations=[Operation("add_texture", {"description": "test"})],
        commitments=[Commitment("canon", "test canon commitment", operation_index=0)],
    )


def _make_world() -> WorldState:
    return WorldState()


class TestRepairStaleContext:
    """Case 1: Turn 5 regression — stale door prose repaired to guardroom prose."""

    def test_repair_replaces_stale_context(self):
        bad_prose = "你蹲在密封的下层门前...发力...门纹丝不动..."
        repaired = "旧卫兵室里积着厚厚一层灰，角落里散落着锈蚀的盔甲碎片。"

        brief = _make_brief()
        flash = _MockFlashClient(repaired)
        result = run_render_repair(
            bad_prose,
            issues=["L2 semantic: intent fulfillment (wrong_target): prose describes pushing door instead of searching guardroom"],
            semantic_judgments=[],
            render_brief=brief,
            client=flash,
        )
        assert "卫兵室" in result or "guardroom" in result.lower()


class TestRepairHiddenTruth:
    """Case 2: Hidden truth symbolic bridge removed by repair."""

    def test_repair_removes_symbolic_bridge(self):
        bad_prose = "三道痕迹像在等待某个声音回应"
        repaired = "门板上有几道旧划痕，看起来是长年磨损留下的。"

        brief = _make_brief()
        flash = _MockFlashClient(repaired)
        result = run_render_repair(
            bad_prose,
            issues=["L2 semantic: hidden truth exposure (symbolic_bridge): three + response creates bell-sequence bridge"],
            semantic_judgments=[],
            render_brief=brief,
            client=flash,
        )
        assert "等待" not in result
        assert "声音" not in result


class TestRepairAbsentNPC:
    """Case 3: Absent NPC removed from prose by repair."""

    def test_repair_removes_absent_npc(self):
        bad_prose = "阿伦在你身后低声说..."
        repaired = "四周寂静无声，只有你自己的脚步声在回荡。"

        brief = _make_brief(absent_entities=["alen"])
        flash = _MockFlashClient(repaired)
        result = run_render_repair(
            bad_prose,
            issues=["L2 semantic: unsupported claim (absent_entity): Alen is not in current location"],
            semantic_judgments=[],
            render_brief=brief,
            client=flash,
        )
        assert "阿伦" not in result


class TestRepairFailClosed:
    """Case 4: Repair impossible — re-check still fails."""

    def test_repair_impossible_stays_failed(self):
        bad_prose = "你蹲在密封的下层门前...发力...门纹丝不动..."
        # Flash returns same bad prose (repair failed)
        flash = _MockFlashClient(bad_prose)
        local = _MockLocalClientHiddenTruthFail()

        brief = _make_brief()
        tx = _make_tx()
        world = _make_world()

        repaired = run_render_repair(
            bad_prose,
            issues=["L2 semantic: hidden truth exposure (symbolic_bridge): leak"],
            semantic_judgments=[],
            render_brief=brief,
            client=flash,
        )
        # Re-check with mock local that always rejects
        re_check = check_rendered_prose(repaired, tx, world, client=local)
        assert re_check["status"] == "failed"


class TestRepairPromptContents:
    """Verify repair prompt includes all grounding sections."""

    def test_prompt_includes_absent_entities(self):
        class CapturingClient:
            def __init__(self):
                self.last_messages = []

            def chat(self, messages, temperature=0.5):
                self.last_messages = messages
                return "修复后的文本。"

        cap = CapturingClient()
        brief = _make_brief(absent_entities=["alen", "ghost"])
        run_render_repair(
            "原文",
            issues=["test issue"],
            semantic_judgments=[],
            render_brief=brief,
            client=cap,
        )
        user_prompt = cap.last_messages[1]["content"]
        assert "Absent Entities" in user_prompt
        assert "alen" in user_prompt
        assert "ghost" in user_prompt

    def test_prompt_includes_player_location(self):
        class CapturingClient:
            def __init__(self):
                self.last_messages = []

            def chat(self, messages, temperature=0.5):
                self.last_messages = messages
                return "修复后的文本。"

        cap = CapturingClient()
        brief = _make_brief(player_location="sealed_chamber")
        run_render_repair(
            "原文",
            issues=["test issue"],
            semantic_judgments=[],
            render_brief=brief,
            client=cap,
        )
        user_prompt = cap.last_messages[1]["content"]
        assert "sealed_chamber" in user_prompt
