"""Unit tests for metarpg.agentic.feasibility (v0.6.6 simplified schema).

LLM-free tests use a MagicMock or a tiny fake client. No live LLM calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.feasibility import run_feasibility
from metarpg.agentic.schemas import FeasibilityReport


def _packet() -> dict:
    return {
        "scene": {
            "location": "greyfen_tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": [],
            "atmosphere": "tense greyfen_tavern (tavern, drink)",
        },
        "player_context": {
            "known_facts": [],
            "recent_events": [],
            "inventory_or_handheld": [],
        },
        "npc_surface": {"mara": {"role": "barkeep", "visible_mood": ["neutral"]}},
        "allowed_effect_kinds": ["transient_event", "journal_note", "observe_reaction"],
        "allowed_reveals": [],
        "forbidden": {"entities_not_present": ["rusk", "iven"]},
    }


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self._text = response_text

    def chat(self, messages, temperature: float = 0.7) -> str:
        return self._text


def test_feasible_false_parsed() -> None:
    raw = json.dumps(
        {
            "feasible": False,
            "feasibility_facts": ["玩家声称使用'光剑',但此世界 schema 无此物"],
            "preserve_player_voice": ["抽出", "光剑", "斩"],
        },
        ensure_ascii=False,
    )
    client = _FakeClient(raw)
    report = run_feasibility(_packet(), "我抽出光剑斩向 Mara", client=client)

    assert isinstance(report, FeasibilityReport)
    assert report.world_response_kind == "absence"
    assert any("光剑" in f for f in report.feasibility_facts)
    assert "斩" in report.preserve_player_voice


def test_feasible_true_parsed() -> None:
    raw = json.dumps(
        {
            "feasible": True,
            "feasibility_facts": [],
            "preserve_player_voice": ["看看"],
        },
        ensure_ascii=False,
    )
    report = run_feasibility(_packet(), "看看周围", client=_FakeClient(raw))
    assert report.world_response_kind == "accept"
    assert report.feasibility_facts == []
    assert "看看" in report.preserve_player_voice


def test_llm_unavailable_falls_back_to_deterministic_filter() -> None:
    """No LLM available: the deterministic schema pre-filter must catch
    obvious schema violations (lightsabers, telepathy)."""
    import metarpg.agentic.feasibility as feas_mod
    original = feas_mod.make_client
    feas_mod.make_client = lambda kind="local": None
    try:
        report = run_feasibility(_packet(), "我抽出光剑斩向 Mara")
    finally:
        feas_mod.make_client = original

    assert report.world_response_kind == "absence"
    assert report.preserve_player_voice  # fallback voice extracted from input


def test_llm_unavailable_neutral_input_defaults_to_accept() -> None:
    """No LLM, no obvious schema violation: default to accept."""
    import metarpg.agentic.feasibility as feas_mod
    original = feas_mod.make_client
    feas_mod.make_client = lambda kind="local": None
    try:
        report = run_feasibility(_packet(), "我环顾四周")
    finally:
        feas_mod.make_client = original

    assert report.world_response_kind == "accept"


def test_friction_kind_parsed() -> None:
    raw = json.dumps(
        {
            "stated_action": "force the door",
            "stated_props": [],
            "stated_targets": ["door"],
            "world_response_kind": "friction",
            "feasibility_facts": ["the door is bolted from the other side"],
            "preserve_player_voice": ["撞", "门"],
        },
        ensure_ascii=False,
    )
    report = run_feasibility(_packet(), "我用力撞门", client=_FakeClient(raw))
    assert report.world_response_kind == "friction"
    assert report.stated_targets == ["door"]


def test_reframing_kind_parsed() -> None:
    raw = json.dumps(
        {
            "stated_action": "read mind",
            "stated_props": [],
            "stated_targets": ["mara"],
            "world_response_kind": "reframing",
            "feasibility_facts": ["telepathy is not part of this world"],
            "preserve_player_voice": ["读取", "心思"],
        },
        ensure_ascii=False,
    )
    report = run_feasibility(_packet(), "我读取 Mara 的心思", client=_FakeClient(raw))
    assert report.world_response_kind == "reframing"
    assert report.stated_action == "read mind"


def test_explicit_accept_kind_parsed() -> None:
    raw = json.dumps(
        {
            "stated_action": "look around",
            "stated_props": [],
            "stated_targets": [],
            "world_response_kind": "accept",
            "feasibility_facts": [],
            "preserve_player_voice": ["看"],
        },
        ensure_ascii=False,
    )
    report = run_feasibility(_packet(), "我看看周围", client=_FakeClient(raw))
    assert report.world_response_kind == "accept"
    assert report.stated_action == "look around"


def test_malformed_json_falls_back_to_accept() -> None:
    """LLM returns garbage — must not crash, must default to accept."""
    report = run_feasibility(_packet(), "测试输入", client=_FakeClient("not json at all"))
    assert report.world_response_kind == "accept"
    assert report.preserve_player_voice  # fallback


def test_json_inside_markdown_fence_parses() -> None:
    raw = "```json\n" + json.dumps({
        "feasible": False,
        "feasibility_facts": ["阻力"],
        "preserve_player_voice": ["抽剑"],
    }, ensure_ascii=False) + "\n```"
    report = run_feasibility(_packet(), "抽剑", client=_FakeClient(raw))
    assert report.world_response_kind == "absence"


def test_empty_preserve_voice_uses_fallback() -> None:
    raw = json.dumps(
        {
            "feasible": False,
            "feasibility_facts": [],
            "preserve_player_voice": [],
        },
        ensure_ascii=False,
    )
    report = run_feasibility(_packet(), "光剑 斩", client=_FakeClient(raw))
    assert report.world_response_kind == "absence"
    assert report.preserve_player_voice  # fallback kicked in
    assert "光剑" in report.preserve_player_voice or "斩" in report.preserve_player_voice


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
