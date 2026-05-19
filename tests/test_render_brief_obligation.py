"""Tests for Current-Turn Render Contract (v0.7.4 Phase 3)."""
from __future__ import annotations

from metarpg.agentic.render_brief import _build_current_turn_obligation
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    RenderBrief,
    TurnTransaction,
)


def _make_tx(source: str, action_type: str, targets: list[str], player_input: str = "") -> TurnTransaction:
    """Helper to build a TurnTransaction with given source/action/targets."""
    return TurnTransaction(
        id="t001",
        player_input=player_input,
        player_intent={"action_type": action_type, "targets": targets, "unresolved": []},
        assumptions=[{"source": source, "reason": "test"}],
        operations=[Operation("test", {})],
        commitments=[Commitment("texture", "test", operation_index=0)],
        narrative_frame=NarrativeFrame(),
    )


class TestAbsenceResponseObligation:
    def test_has_must_not_claim(self):
        tx = _make_tx("absence_response", "ask", ["alen"], "我问艾伦。")
        obl = _build_current_turn_obligation(tx)
        assert obl["response_mode"] == "absence"
        assert "目标不在场/不可达" in obl["must_address"]
        assert "不要渲染前一回合的动作成功" in obl["must_not_claim"]


class TestFallbackObligation:
    def test_forbids_previous_turn_replay(self):
        tx = _make_tx("fallback", "inspect", ["old_guardroom"], "我搜索卫兵室。")
        obl = _build_current_turn_obligation(tx)
        assert obl["response_mode"] == "fallback"
        assert "承认动作无法推进或只给 minimal texture" in obl["must_address"]
        assert "不要渲染前一回合的动作成功" in obl["must_not_claim"]
        assert "不要声称新状态变化发生" in obl["must_not_claim"]


class TestDeterministicMovementObligation:
    def test_must_address_destination(self):
        tx = _make_tx("deterministic_movement", "move", ["entrance_hall"], "我回到入口厅。")
        obl = _build_current_turn_obligation(tx)
        assert obl["response_mode"] == "normal"
        assert "玩家移动到目的地" in obl["must_address"]


class TestDirectorObligation:
    def test_normal_mode_for_director(self):
        tx = _make_tx("director", "inspect", ["sealed_lower_door"], "我检查下层门。")
        obl = _build_current_turn_obligation(tx)
        assert obl["response_mode"] == "normal"
        assert "must_not_claim" not in obl


class TestUnreachableLocationObligation:
    def test_unreachable_mode(self):
        tx = _make_tx("unreachable_location_response", "move", ["sealed_lower_door"], "我回到封闭下层门。")
        obl = _build_current_turn_obligation(tx)
        assert obl["response_mode"] == "unreachable"
        assert "目标地点存在但当前无法直接到达" in obl["must_address"]
        assert "不要渲染玩家已成功到达该地点" in obl["must_not_claim"]


class TestNoAssumptionsDefaultsToDirector:
    def test_defaults_to_director(self):
        tx = TurnTransaction(
            id="t001",
            player_input="我检查门。",
            player_intent={"action_type": "inspect", "targets": ["door"], "unresolved": []},
            assumptions=[],  # no assumptions
        )
        obl = _build_current_turn_obligation(tx)
        assert obl["source"] == "director"
        assert obl["response_mode"] == "normal"
