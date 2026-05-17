"""Tests for deterministic scanner (Phase D)."""
from __future__ import annotations

from metarpg.agentic.scanner import scan_segment


def test_scan_finds_inner_thought_verb():
    text = "玛拉想起矿井密道，手指一颤。"
    findings = scan_segment("s1", text, [], [], ["secret_mine"])
    assert len(findings["inner_thought_verb_hits"]) > 0
    assert any(c.kind == "npc_inner_state" for c in findings["claims"])


def test_scan_finds_hidden_alias():
    text = "她守着一个秘密。"
    findings = scan_segment("s1", text, [], [], ["秘密"])
    assert "秘密" in findings["hidden_fact_alias_hits"]


def test_scan_finds_remote_cue():
    text = "与此同时，守卫站那边传来脚步声。"
    findings = scan_segment("s1", text, [], [], [])
    assert len(findings["remote_event_cue_hits"]) > 0
    assert any(c.kind == "remote_event" for c in findings["claims"])


def test_scan_finds_raw_snake_case():
    text = "你看到了 player_ordered_ale_from_mara 的提示。"
    findings = scan_segment("s1", text, [], [], [])
    assert "player_ordered_ale_from_mara" in findings["raw_event_id_hits"]


def test_scan_ignores_short_snake_case():
    text = " player mara rusk"
    findings = scan_segment("s1", text, [], [], [])
    # Short/common names should not be flagged
    assert "player" not in findings["raw_event_id_hits"]
