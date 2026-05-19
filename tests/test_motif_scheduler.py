"""Tests for motif_scheduler.py — motif scheduling and variation selection."""
from __future__ import annotations

import pytest

from metarpg.agentic.motif_scheduler import (
    MotifSchedule,
    _parse_functions,
    _pick_variation,
    _turns_since_any_motif,
    schedule_motifs,
    update_motif_ledger,
)
from metarpg.agentic.narrative_grammar import NarrativeGrammar
from metarpg.agentic.seed_loader import WorldSeed


def _make_seed() -> WorldSeed:
    seed = WorldSeed()
    seed.motifs = {
        "m_black_ash": {
            "label": "黑灰",
            "function": "clue, contamination, failed protection",
            "allowed_variations": ["fingerprint", "smear", "powder", "line", "bitter smell"],
        },
        "m_bell": {
            "label": "无声的铃",
            "function": "threshold, memory, mechanism",
            "allowed_variations": ["dull metal", "absent chime", "three marks", "vibration"],
        },
        "m_wet_stone": {
            "label": "潮湿石阶",
            "function": "time pressure, depth, danger",
            "allowed_variations": ["echo", "cold water", "moss", "rising line"],
        },
    }
    seed.active_hooks = {
        "hook_black_ash_enigma": {
            "hook_type": "enigma",
            "subject": "black_ash",
            "object": "lower_vault",
            "tension": "黑灰出现在入口门槛,但来源不明。",
        },
        "hook_lower_door_threshold": {
            "hook_type": "threshold",
            "subject": "sealed_lower_door",
            "object": "lower_vault",
            "tension": "下层门封闭,但它明显不是普通锁。",
        },
    }
    return seed


def _make_grammar() -> NarrativeGrammar:
    return NarrativeGrammar(
        motif_rules={"max_motifs_per_turn": 2},
        beat_types={},
        hook_types={},
        commitment_levels={},
        render_rules={},
    )


class TestParseFunctions:
    def test_single(self):
        assert _parse_functions("clue") == {"clue"}

    def test_multiple(self):
        assert _parse_functions("clue, contamination, failed protection") == {
            "clue",
            "contamination",
            "failed protection",
        }


class TestPickVariation:
    def test_first_use(self):
        seed = _make_seed()
        var = _pick_variation("m_black_ash", seed, ledger={})
        assert var == "fingerprint"

    def test_avoid_last(self):
        seed = _make_seed()
        ledger = {"m_black_ash": {"last_variation": "fingerprint"}}
        var = _pick_variation("m_black_ash", seed, ledger=ledger)
        assert var != "fingerprint"

    def test_round_robin(self):
        seed = _make_seed()
        ledger = {"m_black_ash": {"last_variation": "smear"}}
        var = _pick_variation("m_black_ash", seed, ledger=ledger)
        assert var == "powder"


class TestTurnsSinceAnyMotif:
    def test_never_used(self):
        assert _turns_since_any_motif({}, current_turn=5) == 0

    def test_recent(self):
        ledger = {"m_a": {"last_used_turn": 8}}
        assert _turns_since_any_motif(ledger, current_turn=10) == 2

    def test_force_threshold(self):
        ledger = {"m_a": {"last_used_turn": 1}}
        assert _turns_since_any_motif(ledger, current_turn=5) == 4


class TestScheduleMotifs:
    def test_inspection_with_hook(self):
        seed = _make_seed()
        grammar = _make_grammar()
        schedule = schedule_motifs(
            beat="inspection",
            active_hooks=["hook_black_ash_enigma"],
            seed=seed,
            grammar=grammar,
            motif_ledger={},
            current_turn=1,
        )
        assert len(schedule.motifs_to_use) >= 1
        assert "m_black_ash" in schedule.motifs_to_use

    def test_threshold_with_hook(self):
        seed = _make_seed()
        grammar = _make_grammar()
        schedule = schedule_motifs(
            beat="threshold_crossing",
            active_hooks=["hook_lower_door_threshold"],
            seed=seed,
            grammar=grammar,
            motif_ledger={},
            current_turn=1,
        )
        assert len(schedule.motifs_to_use) >= 1
        assert "m_bell" in schedule.motifs_to_use

    def test_mechanical_beat_allows_zero(self):
        seed = _make_seed()
        grammar = _make_grammar()
        schedule = schedule_motifs(
            beat="aftermath",
            active_hooks=[],
            seed=seed,
            grammar=grammar,
            motif_ledger={},
            current_turn=1,
        )
        # aftermath is mechanical → allows zero
        assert len(schedule.motifs_to_use) == 0

    def test_force_after_three_turns(self):
        seed = _make_seed()
        grammar = _make_grammar()
        ledger = {
            "m_black_ash": {"last_used_turn": 1, "use_count": 1},
            "m_bell": {"last_used_turn": 2, "use_count": 1},
        }
        schedule = schedule_motifs(
            beat="aftermath",
            active_hooks=[],
            seed=seed,
            grammar=grammar,
            motif_ledger=ledger,
            current_turn=5,  # 3+ turns since last motif
        )
        # Force 1 even on mechanical beat
        assert len(schedule.motifs_to_use) >= 1

    def test_cooldown_respected(self):
        seed = _make_seed()
        grammar = _make_grammar()
        ledger = {
            "m_black_ash": {"last_used_turn": 5, "use_count": 1},
        }
        schedule = schedule_motifs(
            beat="inspection",
            active_hooks=["hook_black_ash_enigma"],
            seed=seed,
            grammar=grammar,
            motif_ledger=ledger,
            current_turn=6,  # only 1 turn ago → cooldown
        )
        # m_black_ash is on cooldown, so should not be selected
        assert "m_black_ash" not in schedule.motifs_to_use

    def test_max_two(self):
        seed = _make_seed()
        grammar = _make_grammar()
        # Allow up to 2
        schedule = schedule_motifs(
            beat="inspection",
            active_hooks=["hook_black_ash_enigma", "hook_lower_door_threshold"],
            seed=seed,
            grammar=grammar,
            motif_ledger={},
            current_turn=1,
        )
        assert len(schedule.motifs_to_use) <= 2


class TestUpdateLedger:
    def test_basic(self):
        schedule = MotifSchedule(
            motifs_to_use=["m_black_ash"],
            required_variations={"m_black_ash": "bitter smell"},
        )
        new_ledger = update_motif_ledger({}, schedule, current_turn=3)
        assert new_ledger["m_black_ash"]["last_used_turn"] == 3
        assert new_ledger["m_black_ash"]["use_count"] == 1
        assert new_ledger["m_black_ash"]["last_variation"] == "bitter smell"

    def test_immutable(self):
        ledger = {"m_black_ash": {"last_used_turn": 1, "use_count": 1}}
        schedule = MotifSchedule(motifs_to_use=["m_bell"], required_variations={"m_bell": "echo"})
        new_ledger = update_motif_ledger(ledger, schedule, current_turn=2)
        # Original should be unchanged
        assert ledger["m_black_ash"]["last_used_turn"] == 1
        assert "m_bell" in new_ledger
