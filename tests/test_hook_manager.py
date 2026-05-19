from pathlib import Path

from metarpg.agentic.hook_manager import build_narrative_frame
from metarpg.agentic.narrative_grammar import load_grammar
from metarpg.agentic.seed_loader import load_seed

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")
GRAMMAR_PATH = Path("metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml")


def test_inspect_black_ash_engages_enigma_hook():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "inspect", "targets": ["black_ash"], "props": []}
    frame = build_narrative_frame("我检查门槛上的黑灰", intent, seed, grammar)
    assert "hook_black_ash_enigma" in frame.active_hooks
    assert frame.beat == "inspection"
    assert "hint_ash_smell" in frame.candidate_hints


def test_ask_alen_surfaces_debt_hook():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "ask", "targets": ["alen"], "props": ["black_ash"]}
    frame = build_narrative_frame("我问艾伦这灰是怎么回事", intent, seed, grammar)
    assert "hook_alen_debt" in frame.active_hooks
    assert frame.beat == "social_pressure"


def test_approach_lower_door_surfaces_threshold():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "move", "targets": ["lower_door"], "props": []}
    frame = build_narrative_frame("我去看那扇封闭的下层门", intent, seed, grammar)
    assert "hook_lower_door_threshold" in frame.active_hooks
    assert frame.beat == "threshold_crossing"
    # Dormant hook should be surfaced
    assert seed.active_hooks["hook_lower_door_threshold"]["status"] == "surfaced"


def test_motif_limit():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "inspect", "targets": ["black_ash"], "props": []}
    frame = build_narrative_frame("我检查门槛上的黑灰", intent, seed, grammar)
    max_motifs = grammar.motif_rules.get("max_motifs_per_turn", 2)
    assert len(frame.motifs_to_use) <= max_motifs


def test_forbidden_moves_include_npc_inner_monologue():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "inspect", "targets": ["black_ash"], "props": []}
    frame = build_narrative_frame("我检查门槛上的黑灰", intent, seed, grammar)
    assert "npc_inner_monologue" in frame.forbidden_moves


def test_threshold_hook_blocks_direct_reveal():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "move", "targets": ["lower_door"], "props": []}
    frame = build_narrative_frame("我去看那扇封闭的下层门", intent, seed, grammar)
    assert "direct_hidden_truth_reveal" in frame.forbidden_moves


def test_allowed_commitments_for_inspection():
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    intent = {"action_type": "inspect", "targets": ["black_ash"], "props": []}
    frame = build_narrative_frame("我检查门槛上的黑灰", intent, seed, grammar)
    assert "hint" in frame.allowed_commitment_levels
    assert "affordance" in frame.allowed_commitment_levels
