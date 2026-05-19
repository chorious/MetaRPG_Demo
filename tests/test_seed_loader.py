from pathlib import Path

import pytest

from metarpg.agentic.narrative_grammar import load_grammar
from metarpg.agentic.seed_loader import load_seed

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")
GRAMMAR_PATH = Path("metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml")


def test_load_seed_entities():
    seed = load_seed(SEED_PATH)
    assert "player" in seed.entities
    assert "alen" in seed.entities
    assert seed.entities["alen"]["visible_name"] == "艾伦"


def test_load_seed_locations_and_items():
    seed = load_seed(SEED_PATH)
    assert "entrance_hall" in seed.locations
    assert "sealed_lower_door" in seed.locations
    assert "black_ash" in seed.items


def test_load_seed_beliefs_and_hooks():
    seed = load_seed(SEED_PATH)
    assert "b_alen_hides_key" in seed.beliefs
    assert "hook_black_ash_enigma" in seed.active_hooks
    assert "hook_lower_door_threshold" in seed.active_hooks


def test_load_seed_canon_facts():
    seed = load_seed(SEED_PATH)
    predicates = {f["predicate"] for f in seed.canon_facts}
    assert "at" in predicates
    assert "has" in predicates


def test_load_grammar_hook_types():
    grammar = load_grammar(GRAMMAR_PATH)
    expected = {"lack", "enigma", "threshold", "debt", "contradiction", "threat_timer"}
    assert expected.issubset(set(grammar.hook_types.keys()))


def test_load_grammar_beat_types():
    grammar = load_grammar(GRAMMAR_PATH)
    assert "inspection" in grammar.beat_types
    assert "threshold_crossing" in grammar.beat_types
    assert "social_pressure" in grammar.beat_types


def test_load_grammar_commitment_levels():
    grammar = load_grammar(GRAMMAR_PATH)
    expected = {"texture", "hint", "affordance", "event", "canon", "utterance", "belief_evidence"}
    assert expected.issubset(set(grammar.commitment_levels.keys()))


def test_load_grammar_render_rules():
    grammar = load_grammar(GRAMMAR_PATH)
    assert grammar.render_rules.get("prose_language") == "zh"
    assert grammar.render_rules.get("npc_inner_monologue_forbidden") is True


# ---------------------------------------------------------------------------
# v0.7.1 — Alias resolution tests
# ---------------------------------------------------------------------------


def test_resolve_alias_exact_match():
    seed = load_seed(SEED_PATH)
    results = seed.resolve_alias("下层门")
    assert len(results) >= 1
    cids = {r[0] for r in results}
    assert "sealed_lower_door" in cids


def test_resolve_alias_item():
    seed = load_seed(SEED_PATH)
    results = seed.resolve_alias("黑灰")
    assert len(results) >= 1
    kinds = {r[1] for r in results}
    assert "item" in kinds or "motif" in kinds


def test_resolve_alias_entity():
    seed = load_seed(SEED_PATH)
    results = seed.resolve_alias("艾伦")
    assert len(results) >= 1
    cids = {r[0] for r in results}
    assert "alen" in cids


def test_resolve_alias_containment_match():
    """Mention containing a known alias should resolve with lower confidence."""
    seed = load_seed(SEED_PATH)
    results = seed.resolve_alias("我去看那扇封闭的下层门")
    assert len(results) >= 1
    cids = {r[0] for r in results}
    assert "sealed_lower_door" in cids
    # containment matches get 0.85 confidence
    assert any(conf == 0.85 for _, _, conf in results)


def test_resolve_alias_no_match():
    seed = load_seed(SEED_PATH)
    results = seed.resolve_alias("完全不存在的词")
    assert results == []


def test_get_aliases_for():
    seed = load_seed(SEED_PATH)
    aliases = seed.get_aliases_for("sealed_lower_door")
    assert any("下层门" in a for a in aliases)


def test_alias_index_built_on_load():
    seed = load_seed(SEED_PATH)
    assert seed._alias_index  # non-empty after load_seed
    assert "下层门" in seed._alias_index
    assert "黑灰" in seed._alias_index
    assert "艾伦" in seed._alias_index
