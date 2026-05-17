"""MetaAct extraction tests."""
from __future__ import annotations

from metarpg.metaact import build_metaact
from metarpg.scenarios.greyfen import build


def _world():
    return build()


def test_extracts_quoted_speech():
    w = _world()
    meta = build_metaact('耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"', w)
    assert "嘿，给我一杯麦芽啤酒" in meta.speech_fragments


def test_extracts_surface_cues_chinese():
    w = _world()
    meta = build_metaact("问问玛拉附近有什么大事", w)
    cues = set(meta.surface_cues)
    assert "玛拉" in cues


def test_metaact_local_entities_from_world():
    w = _world()
    meta = build_metaact("观察周围", w)
    assert "mara" in meta.local_entities
    assert meta.player_location == "tavern"


def test_metaact_empty_input():
    w = _world()
    meta = build_metaact("", w)
    assert meta.raw_text == ""
    assert meta.local_entities == ["mara"]
