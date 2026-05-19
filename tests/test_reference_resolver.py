"""Tests for reference_resolver.py -- L1 canonical ID resolution."""
from __future__ import annotations

import pytest

from metarpg.agentic.reference_resolver import (
    _infer_action_type,
    resolve_references,
)


class TestInferActionType:
    def test_move_chinese(self):
        assert _infer_action_type("我去下层门") == "move"
        assert _infer_action_type("走到入口厅") == "move"

    def test_inspect_chinese(self):
        assert _infer_action_type("检查黑灰") == "inspect"
        assert _infer_action_type("看看那扇门") == "inspect"

    def test_speak_chinese(self):
        assert _infer_action_type("问艾伦") == "speak"
        assert _infer_action_type("告诉他真相") == "speak"

    def test_ambiguous(self):
        assert _infer_action_type("嗯……") == "ambiguous"


class TestResolveReferencesDeterministic:
    """Tests that do NOT require a live LLM client."""

    def test_exact_alias_location(self):
        aliases = {
            "sealed_lower_door": ["下层门", "lower door"],
            "alen": ["艾伦"],
        }
        intent = resolve_references(
            player_input="我去下层门",
            known_entities=["alen"],
            known_items=[],
            known_locations=["sealed_lower_door"],
            known_hooks=[],
            known_motifs=[],
            aliases_map=aliases,
            available_entities=["alen"],
            available_items=[],
            available_locations=["sealed_lower_door"],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        assert len(intent.targets) >= 1
        cids = {t.canonical_id for t in intent.targets}
        assert "sealed_lower_door" in cids

    def test_exact_alias_entity(self):
        aliases = {"alen": ["艾伦", "Alen"]}
        intent = resolve_references(
            player_input="艾伦在哪里",
            known_entities=["alen"],
            known_items=[],
            known_locations=[],
            known_hooks=[],
            known_motifs=[],
            aliases_map=aliases,
            available_entities=["alen"],
            available_items=[],
            available_locations=[],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        cids = {t.canonical_id for t in intent.targets}
        assert "alen" in cids

    def test_containment_match(self):
        aliases = {"sealed_lower_door": ["下层门"]}
        intent = resolve_references(
            player_input="我去看那扇封闭的下层门",
            known_entities=[],
            known_items=[],
            known_locations=["sealed_lower_door"],
            known_hooks=[],
            known_motifs=[],
            aliases_map=aliases,
            available_entities=[],
            available_items=[],
            available_locations=["sealed_lower_door"],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        cids = {t.canonical_id for t in intent.targets}
        assert "sealed_lower_door" in cids
        # containment matches get 0.85
        assert any(t.confidence == 0.85 for t in intent.targets)

    def test_no_match(self):
        intent = resolve_references(
            player_input="完全不存在的词",
            known_entities=[],
            known_items=[],
            known_locations=[],
            known_hooks=[],
            known_motifs=[],
            aliases_map={},
            available_entities=[],
            available_items=[],
            available_locations=[],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        assert intent.unresolved == ["完全不存在的词"]
        assert intent.targets == []
        assert intent.props == []

    def test_item_as_prop(self):
        aliases = {"black_ash": ["黑灰", "灰烬"]}
        intent = resolve_references(
            player_input="这黑灰是怎么回事",
            known_entities=[],
            known_items=["black_ash"],
            known_locations=[],
            known_hooks=[],
            known_motifs=[],
            aliases_map=aliases,
            available_entities=[],
            available_items=["black_ash"],
            available_locations=[],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        cids = {p.canonical_id for p in intent.props}
        assert "black_ash" in cids
        assert all(p.kind == "item" for p in intent.props)

    def test_hook_alias(self):
        aliases = {"hook_black_ash_enigma": ["黑灰之谜", "ash mystery"]}
        intent = resolve_references(
            player_input="黑灰之谜到底是什么",
            known_entities=[],
            known_items=[],
            known_locations=[],
            known_hooks=["hook_black_ash_enigma"],
            known_motifs=[],
            aliases_map=aliases,
            available_entities=[],
            available_items=[],
            available_locations=[],
            available_hooks=["hook_black_ash_enigma"],
            available_motifs=[],
            client=None,
        )
        cids = {p.canonical_id for p in intent.props}
        assert "hook_black_ash_enigma" in cids

    def test_empty_input(self):
        intent = resolve_references(
            player_input="",
            known_entities=[],
            known_items=[],
            known_locations=[],
            known_hooks=[],
            known_motifs=[],
            aliases_map={},
            available_entities=[],
            available_items=[],
            available_locations=[],
            available_hooks=[],
            available_motifs=[],
            client=None,
        )
        assert intent.action_type == "none"
