"""Hypothesis proposer tests — v0.2 free-form input interpretation."""
from __future__ import annotations

from metarpg.engine import Engine
from metarpg.metaact import build_metaact
from metarpg.narrator import Narrator
from metarpg.proposer import propose, select_best
from metarpg.scenarios.greyfen import build, build_hooks


def _engine():
    w = build()
    hooks = build_hooks()
    return Engine(w, narrator=Narrator(enabled=False), hooks=hooks)


def test_propose_chinese_local_news_question():
    e = _engine()
    meta = build_metaact("问问玛拉附近有什么大事", e.world)
    hyps = propose(meta, e.world, e.hooks)
    best = select_best(hyps)
    assert best is not None
    assert best.act_kind == "ask_about_topic"
    assert best.target == "mara"


def test_order_ale_hypothesis():
    e = _engine()
    meta = build_metaact('耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"', e.world)
    hyps = propose(meta, e.world, e.hooks)
    best = select_best(hyps)
    assert best is not None
    assert best.act_kind == "order_drink"
    assert best.target == "mara"


def test_complain_no_beer_hypothesis():
    e = _engine()
    meta = build_metaact("怎么回事，你们酒馆甚至没有酒么！", e.world)
    hyps = propose(meta, e.world, e.hooks)
    best = select_best(hyps)
    assert best is not None
    assert best.act_kind == "complain_about_service"


def test_ambiguous_social_fallback():
    e = _engine()
    meta = build_metaact("你这里的影子看起来很旧", e.world)
    hyps = propose(meta, e.world, e.hooks)
    best = select_best(hyps)
    assert best is not None
    assert best.act_kind == "ambiguous_social_act"


def test_no_unparseable_near_npc():
    """Non-empty input near an NPC should produce a hypothesis (even if rejected later)."""
    e = _engine()
    for text in ("随便说点什么", "看看周围", "你在想什么"):
        meta = build_metaact(text, e.world)
        hyps = propose(meta, e.world, e.hooks)
        assert len(hyps) > 0
        best = select_best(hyps)
        assert best is not None


def test_high_confidence_command_path():
    """Well-formed commands still use Path A with high confidence."""
    e = _engine()
    meta = build_metaact("ask Mara about the mine", e.world)
    hyps = propose(meta, e.world, e.hooks)
    best = select_best(hyps)
    assert best.confidence >= 0.90


def test_free_form_ask_validates_and_produces_patch():
    """End-to-end: free-form ask produces accepted patch."""
    e = _engine()
    rec = e.step("问问玛拉附近有什么大事")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "ask_about_topic"


def test_free_form_order_produces_accepted_patch():
    e = _engine()
    rec = e.step('耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"')
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "order_drink"


def test_free_form_complain_produces_accepted_patch():
    e = _engine()
    rec = e.step("怎么回事，你们酒馆甚至没有酒么！")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "complain_about_service"
