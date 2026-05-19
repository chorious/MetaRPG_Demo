"""Tests for Unreachable Location Response (v0.7.4 Phase 4)."""
from __future__ import annotations

from metarpg.agentic.runner import _build_unreachable_response_tx
from metarpg.agentic.transaction import NarrativeFrame


class MockRef:
    def __init__(self, canonical_id: str, kind: str = "location", available: bool = True):
        self.canonical_id = canonical_id
        self.kind = kind
        self.available = available


class TestUnreachableResponseTx:
    def test_builds_unreachable_tx(self):
        ref = MockRef("sealed_lower_door")
        tx = _build_unreachable_response_tx(
            "我回到封闭下层门。",
            ref,
            NarrativeFrame(),
            draft_id="d001",
        )
        assert tx.id == "d001"
        assert tx.player_input == "我回到封闭下层门。"
        assert tx.assumptions[0]["source"] == "unreachable_location_response"
        assert tx.assumptions[0]["target"] == "sealed_lower_door"
        ops = tx.operations
        assert ops[0].kind == "add_texture"
        assert "sealed lower door" in ops[0].params["description"].lower()
        assert ops[1].kind == "add_event"
        assert "unreachable" in ops[1].params["summary"].lower()

    def test_does_not_move_player(self):
        ref = MockRef("old_guardroom")
        tx = _build_unreachable_response_tx("我去卫兵室。", ref, NarrativeFrame())
        kinds = [op.kind for op in tx.operations]
        assert "move_player" not in kinds
