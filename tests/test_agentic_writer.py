"""Tests for agentic writer agent (Phase C)."""
from __future__ import annotations

import json

from metarpg.agentic.writer_agent import _build_prompt, _parse_json_safe
from metarpg.agentic.schemas import WriterOutput


def test_build_prompt_contains_player_input():
    pkt = {
        "current_scene": {"location": "tavern"},
        "player_context": {"known_facts": []},
        "interaction_context": {},
        "allowed_effect_kinds": ["consume_item"],
        "forbidden": {},
    }
    prompt = _build_prompt(pkt, "一饮而尽")
    assert "一饮而尽" in prompt
    assert "consume_item" in prompt


def test_parse_json_safe_strips_fences():
    raw = '```json\n{"interpretation": "test"}\n```'
    parsed = _parse_json_safe(raw)
    assert parsed["interpretation"] == "test"


def test_parse_json_safe_plain_json():
    raw = '{"interpretation": "plain"}'
    parsed = _parse_json_safe(raw)
    assert parsed["interpretation"] == "plain"
