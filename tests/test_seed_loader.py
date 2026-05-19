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
