"""Tests for post_render_checker.py (Phase 7)."""
from __future__ import annotations

import pytest

from metarpg.agentic.post_render_checker import check_rendered_prose
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    RenderBrief,
    TurnTransaction,
)
from metarpg.models import WorldState


def _make_tx() -> TurnTransaction:
    return TurnTransaction(
        id="t1",
        player_input="inspect ash",
        player_intent={"action": "inspect"},
        narrative_frame=NarrativeFrame(beat="inspection"),
        operations=[],
        commitments=[],
        render_brief=RenderBrief(),
        forbidden_claims=[],
        assumptions=[],
    )


def _world_with_hidden_truths() -> WorldState:
    world = WorldState()
    world.hidden_truths = {
        "ht_door": {
            "aliases": ["三重封印", "禁忌之门"],
            "reveal_level": "secret",
        }
    }
    return world


# ---------------------------------------------------------------------------
# Hidden truth alias leaks
# ---------------------------------------------------------------------------


def test_alias_leak_detected():
    world = _world_with_hidden_truths()
    tx = _make_tx()
    prose = "你看到了禁忌之门在发光。"
    result = check_rendered_prose(prose, tx, world)
    assert result["status"] == "light_repair"
    assert any("禁忌之门" in issue for issue in result["issues"])


def test_alias_leak_case_insensitive():
    world = _world_with_hidden_truths()
    tx = _make_tx()
    prose = "三重封印的传说流传已久。"
    result = check_rendered_prose(prose, tx, world)
    assert result["status"] == "light_repair"
    assert any("三重封印" in issue for issue in result["issues"])


def test_no_alias_leak():
    world = _world_with_hidden_truths()
    tx = _make_tx()
    prose = "门槛上的黑灰在火光下泛着细密的颗粒感。"
    result = check_rendered_prose(prose, tx, world)
    assert result["status"] == "pass"


# ---------------------------------------------------------------------------
# NPC inner monologue
# ---------------------------------------------------------------------------


def test_npc_inner_monologue_detected():
    tx = _make_tx()
    prose = "艾伦心想：他到底知道多少？"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "light_repair"
    assert any("inner monologue" in issue for issue in result["issues"])


def test_npc_inner_multiple_indicators():
    tx = _make_tx()
    prose = "他在心里默念着，心底泛起一丝疑虑。"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "light_repair"
    # Only one issue even if multiple indicators hit
    assert sum(1 for i in result["issues"] if "inner monologue" in i) == 1


def test_no_npc_inner_monologue():
    tx = _make_tx()
    prose = "你觉得有些不安。"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "pass"


# ---------------------------------------------------------------------------
# Debug / system terms
# ---------------------------------------------------------------------------


def test_debug_term_detected():
    tx = _make_tx()
    prose = "DEBUG: 场景加载完成。"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "light_repair"
    assert any("Debug" in issue for issue in result["issues"])


def test_system_term_detected():
    tx = _make_tx()
    prose = "SYSTEM 提示：TRANSACTION 已提交。"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "light_repair"


def test_no_debug_terms():
    tx = _make_tx()
    prose = "石阶潮湿而冰冷。"
    result = check_rendered_prose(prose, tx, WorldState())
    assert result["status"] == "pass"


# ---------------------------------------------------------------------------
# Motif variation pass
# ---------------------------------------------------------------------------


def test_motif_variation_passes():
    world = WorldState()
    tx = _make_tx()
    prose = "黑灰如丝绒般覆盖在门槛上，空气中弥漫着微弱的焦糊气息。"
    result = check_rendered_prose(prose, tx, world)
    assert result["status"] == "pass"
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# Multiple violations
# ---------------------------------------------------------------------------


def test_multiple_violations_all_reported():
    world = _world_with_hidden_truths()
    tx = _make_tx()
    prose = "DEBUG: 艾伦心想，禁忌之门即将开启。"
    result = check_rendered_prose(prose, tx, world)
    assert result["status"] == "light_repair"
    assert len(result["issues"]) == 3  # alias, inner monologue, debug
