"""Tests for deterministic movement path (v0.7.3 Phase 1)."""
from __future__ import annotations

import pytest

from metarpg.agentic.runner import _build_deterministic_move_tx, _resolve_move_target
from metarpg.agentic.transaction import NarrativeFrame, Operation


class TestResolveMoveTarget:
    def test_exact_match(self):
        class FakeRef:
            canonical_id = "flooded_stair"
            kind = "location"
            available = True

        class FakeIntent:
            action_type = "move"
            targets = [FakeRef()]

        assert _resolve_move_target(FakeIntent(), ["flooded_stair"]) == "flooded_stair"

    def test_not_move_action(self):
        class FakeRef:
            canonical_id = "flooded_stair"
            kind = "location"
            available = True

        class FakeIntent:
            action_type = "inspect"
            targets = [FakeRef()]

        assert _resolve_move_target(FakeIntent(), ["flooded_stair"]) is None

    def test_multiple_targets(self):
        class FakeRef:
            canonical_id = "flooded_stair"
            kind = "location"
            available = True

        class FakeIntent:
            action_type = "move"
            targets = [FakeRef(), FakeRef()]

        assert _resolve_move_target(FakeIntent(), ["flooded_stair"]) is None

    def target_not_location(self):
        class FakeRef:
            canonical_id = "alen"
            kind = "entity"
            available = True

        class FakeIntent:
            action_type = "move"
            targets = [FakeRef()]

        assert _resolve_move_target(FakeIntent(), []) is None

    def test_not_available(self):
        class FakeRef:
            canonical_id = "flooded_stair"
            kind = "location"
            available = False

        class FakeIntent:
            action_type = "move"
            targets = [FakeRef()]

        assert _resolve_move_target(FakeIntent(), ["flooded_stair"]) is None

    def test_not_reachable(self):
        class FakeRef:
            canonical_id = "secret_vault"
            kind = "location"
            available = True

        class FakeIntent:
            action_type = "move"
            targets = [FakeRef()]

        assert _resolve_move_target(FakeIntent(), ["flooded_stair"]) is None


class TestBuildDeterministicMoveTx:
    def test_structure(self):
        frame = NarrativeFrame(beat="threshold_crossing")
        tx = _build_deterministic_move_tx(
            player_input="我去下层门",
            target_id="sealed_lower_door",
            frame=frame,
            draft_id="test_001",
        )
        assert tx.id == "test_001"
        assert len(tx.operations) == 2
        assert tx.operations[0].kind == "move_player"
        assert tx.operations[0].params["destination"] == "sealed_lower_door"
        assert tx.operations[1].kind == "add_event"
        assert len(tx.commitments) == 2
        assert tx.commitments[0].level == "canon"
        assert tx.commitments[1].level == "event"
        assert tx.assumptions[0]["source"] == "deterministic_movement"

    def test_no_director_call_needed(self):
        """Deterministic tx must have source so analyzer knows Director was skipped."""
        tx = _build_deterministic_move_tx(
            player_input="我去积水阶梯",
            target_id="flooded_stair",
            frame=NarrativeFrame(),
        )
        assert any(a.get("source") == "deterministic_movement" for a in tx.assumptions)
