"""Tests for hook ID integrity (v0.7.2.1)."""
from __future__ import annotations

import pytest

from metarpg.agentic.hook_manager import _match_hooks_v071
from metarpg.agentic.seed_loader import WorldSeed
from metarpg.agentic.semantic_judge import SemanticJudgment


def _make_seed() -> WorldSeed:
    return WorldSeed(
        locations={
            "entrance_hall": {"aliases": ["入口厅"]},
            "flooded_stair": {"aliases": ["积水阶梯"]},
        },
        entities={"alen": {"aliases": ["艾伦"]}, "player": {"aliases": []}},
        items={},
        active_hooks={
            "hook_alen_debt": {
                "id": "hook_alen_debt",
                "hook_type": "lack",
                "subject": "alen",
                "object": "safety",
                "aliases": ["艾伦的债务"],
            },
            "hook_black_ash_enigma": {
                "id": "hook_black_ash_enigma",
                "hook_type": "enigma",
                "subject": "black_ash",
                "object": "lower_vault",
                "aliases": ["黑灰之谜"],
            },
        },
        motifs={},
    )


def test_semantic_judgment_has_optional_hook_id():
    """SemanticJudgment.hook_id is optional and defaults to None."""
    j = SemanticJudgment(
        verdict="pass",
        category="social",
        evidence="test",
        suggested_downgrade=None,
        confidence=0.9,
    )
    assert j.hook_id is None
    j2 = SemanticJudgment(
        verdict="pass",
        category="social",
        evidence="test",
        suggested_downgrade=None,
        confidence=0.9,
        hook_id="hook_alen_debt",
    )
    assert j2.hook_id == "hook_alen_debt"


def test_exact_match_uses_canonical_hook_id():
    """Exact subject match produces canonical hook id."""
    seed = _make_seed()
    matched, judgments = _match_hooks_v071(
        action="speak",
        resolved_targets=["alen"],
        resolved_props=[],
        seed=seed,
    )
    assert "hook_alen_debt" in matched
    assert all(h in seed.active_hooks for h in matched)


def test_non_canonical_hook_id_ignored(monkeypatch) -> None:
    """Semantic judge returning non-canonical hook_id must be ignored."""
    seed = _make_seed()

    fake_judgment = SemanticJudgment(
        verdict="pass",
        category="investigation",
        evidence="test",
        suggested_downgrade=None,
        confidence=0.9,
        hook_id="investigation",
    )

    import metarpg.agentic.semantic_judge as sj
    monkeypatch.setattr(sj, "judge_hook_relevance", lambda **kwargs: [fake_judgment])

    matched, judgments = _match_hooks_v071(
        action="inspect",
        resolved_targets=["black_ash"],
        resolved_props=[],
        seed=seed,
        player_input="test",
        client=object(),
    )
    assert "investigation" not in matched
    assert all(h in seed.active_hooks for h in matched)
    ignored = [j for j in judgments if j.get("verdict") == "ignored"]
    assert len(ignored) == 1
    assert ignored[0]["category"] == "investigation"


def test_canonical_hook_id_from_judge_accepted(monkeypatch) -> None:
    """Semantic judge returning canonical hook_id must be accepted."""
    seed = _make_seed()

    fake_judgment = SemanticJudgment(
        verdict="pass",
        category="debt_revelation",
        evidence="test",
        suggested_downgrade=None,
        confidence=0.9,
        hook_id="hook_alen_debt",
    )

    import metarpg.agentic.semantic_judge as sj
    monkeypatch.setattr(sj, "judge_hook_relevance", lambda **kwargs: [fake_judgment])

    matched, judgments = _match_hooks_v071(
        action="inspect",
        resolved_targets=["torch", "alen"],
        resolved_props=[],
        seed=seed,
        player_input="test",
        client=object(),
    )
    assert "hook_alen_debt" in matched
    assert all(h in seed.active_hooks for h in matched)
    pass_judgments = [j for j in judgments if j.get("verdict") == "pass"]
    assert any(j.get("hook_id") == "hook_alen_debt" for j in pass_judgments)


def test_category_not_polluting_active_hooks(monkeypatch) -> None:
    """Category field must never enter active_hooks list."""
    seed = _make_seed()

    fake_judgment = SemanticJudgment(
        verdict="pass",
        category="environmental_mystery",
        evidence="test",
        suggested_downgrade=None,
        confidence=0.9,
        hook_id="hook_black_ash_enigma",
    )

    import metarpg.agentic.semantic_judge as sj
    monkeypatch.setattr(sj, "judge_hook_relevance", lambda **kwargs: [fake_judgment])

    matched, judgments = _match_hooks_v071(
        action="inspect",
        resolved_targets=["torch", "black_ash"],  # black_ash exact-matches hook_black_ash_enigma
        resolved_props=[],
        seed=seed,
        player_input="test",
        client=object(),
    )
    assert "environmental_mystery" not in matched
    assert "hook_black_ash_enigma" in matched  # from exact match + L2
    pass_j = [j for j in judgments if j.get("verdict") == "pass"][0]
    assert pass_j["hook_id"] == "hook_black_ash_enigma"
    assert pass_j["category"] == "environmental_mystery"
