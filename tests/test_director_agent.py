from pathlib import Path

import pytest

from metarpg.agentic.director_agent import run_director
from metarpg.agentic.hook_manager import build_narrative_frame
from metarpg.agentic.narrative_grammar import load_grammar
from metarpg.agentic.seed_loader import load_seed
from metarpg.agentic.transaction import NarrativeFrame, TurnTransaction

SEED_PATH = Path("metarpg/data/seeds/dnd_ashen_vault_seed.yaml")
GRAMMAR_PATH = Path("metarpg/data/narrative_grammar/dnd_dungeon_grammar.yaml")


class _MockClient:
    """Mock LlmClient that returns preset chat_json responses."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.call_count = 0

    def chat_json(self, messages: list[dict], temperature: float = 0.4) -> dict:
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


def _make_frame(player_input: str, intent: dict) -> NarrativeFrame:
    seed = load_seed(SEED_PATH)
    grammar = load_grammar(GRAMMAR_PATH)
    return build_narrative_frame(player_input, intent, seed, grammar)


def test_director_inspect_black_ash():
    frame = _make_frame("我检查门槛上的黑灰", {"action_type": "inspect", "targets": ["black_ash"], "props": []})
    mock_response = {
        "operations": [{"kind": "inspect", "params": {"target": "black_ash"}}],
        "commitments": [
            {"level": "event", "description": "Player inspects black ash", "operation_index": 0},
            {"level": "hint", "description": "The ash smells bitter", "operation_index": 0},
            {"level": "affordance", "description": "compare_ash", "operation_index": 0},
        ],
    }
    client = _MockClient([mock_response])
    tx = run_director("我检查门槛上的黑灰", frame, {"scene": {}}, client)
    assert any(op.kind == "inspect" for op in tx.operations)
    assert any(c.level == "hint" for c in tx.commitments)
    assert any(c.level == "affordance" for c in tx.commitments)


def test_director_ask_alen():
    frame = _make_frame("我问艾伦这灰是怎么回事", {"action_type": "ask", "targets": ["alen"], "props": ["black_ash"]})
    mock_response = {
        "operations": [{"kind": "speak", "params": {"entity": "alen", "speech_type": "evasive"}}],
        "commitments": [
            {"level": "utterance", "description": "Alen avoids the question", "operation_index": 0},
            {"level": "belief_evidence", "description": "Alen knows more than he says", "operation_index": 0},
        ],
    }
    client = _MockClient([mock_response])
    tx = run_director("我问艾伦这灰是怎么回事", frame, {"scene": {}}, client)
    assert any(op.kind == "speak" for op in tx.operations)
    assert any(c.level == "utterance" for c in tx.commitments)
    assert any(c.level == "belief_evidence" for c in tx.commitments)
    assert not any(c.level == "canon" for c in tx.commitments)


def test_director_retry_once_then_success():
    frame = _make_frame("我检查门槛上的黑灰", {"action_type": "inspect", "targets": ["black_ash"], "props": []})
    bad = {"operations": "not_a_list"}  # schema violation
    good = {
        "operations": [{"kind": "inspect", "params": {"target": "black_ash"}}],
        "commitments": [{"level": "event", "description": "Player inspects black ash", "operation_index": 0}],
    }
    client = _MockClient([bad, good])
    tx = run_director("我检查门槛上的黑灰", frame, {"scene": {}}, client, max_retries=1)
    assert client.call_count == 2
    assert any(op.kind == "inspect" for op in tx.operations)


def test_director_fallback_after_retries():
    frame = _make_frame("我检查门槛上的黑灰", {"action_type": "inspect", "targets": ["black_ash"], "props": []})
    bad = {"operations": "not_a_list"}
    client = _MockClient([bad, bad])
    tx = run_director("我检查门槛上的黑灰", frame, {"scene": {}}, client, max_retries=1)
    assert client.call_count == 2
    assert tx.operations[0].kind == "inner_monologue"
    assert any(a.get("source") == "fallback" for a in tx.assumptions)


def test_director_no_prose_output():
    frame = _make_frame("我检查门槛上的黑灰", {"action_type": "inspect", "targets": ["black_ash"], "props": []})
    mock_response = {
        "operations": [{"kind": "inspect", "params": {"target": "black_ash"}}],
        "commitments": [{"level": "event", "description": "Player inspects black ash", "operation_index": 0}],
    }
    client = _MockClient([mock_response])
    tx = run_director("我检查门槛上的黑灰", frame, {"scene": {}}, client)
    # Director should never output prose segments; only structured operations
    for op in tx.operations:
        assert op.kind in {"inspect", "speak", "move_player", "observe_reaction",
                           "transfer_item", "update_relation", "update_belief",
                           "mark_hook_status", "add_event", "add_texture", "inner_monologue"}


def test_director_forbidden_move_rejected():
    frame = _make_frame("我去看那扇封闭的下层门", {"action_type": "move", "targets": ["lower_door"], "props": []})
    # Mock response includes forbidden npc_inner_monologue operation
    mock_response = {
        "operations": [{"kind": "inner_monologue", "params": {"entity": "alen", "text": "I am scared"}}],
        "commitments": [{"level": "texture", "description": "Alen is scared", "operation_index": 0}],
    }
    client = _MockClient([mock_response])
    tx = run_director("我去看那扇封闭的下层门", frame, {"scene": {}}, client, max_retries=0)
    # Should fallback because forbidden move detected
    assert tx.operations[0].kind == "inner_monologue"  # fallback uses player inner monologue
    assert any(a.get("source") == "fallback" for a in tx.assumptions)
