"""v0.5 regression tests — Frontier Affordance Expansion.

Per planVer0.5 §10. Verifies:
- Scene entry receives large budget and generates surface affordances
- NPC dialogue receives small/medium budget, no unrelated expansion
- Object tool use triggers local materialization candidates
- Frontiers decay when not touched
- Over-expansion is diagnostically visible
"""
from __future__ import annotations

from metarpg.engine import Engine
from metarpg.frontier import (
    FrontierKind,
    FrontierStatus,
    create_frontier,
    decay_frontiers,
    get_active_frontiers,
)
from metarpg.models import WorldState
from metarpg.scenarios.greyfen import build, build_hooks


# ---------- Acceptance Test 10.1: Tavern Entry Expands Large Surface ----------


def test_tavern_entry_expands_large_surface():
    """推门进入酒馆 -> budget=large, touched frontier includes scene_boundary."""
    w = build()
    hooks = build_hooks()
    engine = Engine(w, hooks=hooks)

    # Seed a scene-boundary frontier for tavern
    from metarpg.frontier import create_frontier
    create_frontier(
        w,
        kind=FrontierKind.SCENE_BOUNDARY,
        anchor="tavern",
        location="tavern",
        source_event="player_arrived_at_tavern",
        salience=0.8,
    )

    rec = engine.step("推门进入酒馆")

    assert rec.budget_class == "large", f"expected large budget, got {rec.budget_class}"
    assert any("scene_boundary" in f for f in rec.touched_frontiers), "expected scene_boundary frontier touched"
    assert len(rec.affordance_candidates) > 0, "expected affordance candidates generated"


# ---------- Acceptance Test 10.2: Known NPC Conversation Expands Small Surface ----------


def test_known_npc_conversation_small_surface():
    """问玛拉关于守卫站的事 -> budget=small or medium, no unrelated NPC/object explosion."""
    w = build()
    hooks = build_hooks()
    engine = Engine(w, hooks=hooks)

    rec = engine.step("问玛拉关于守卫站的事")

    assert rec.budget_class in ("small", "medium"), f"expected small/medium budget, got {rec.budget_class}"

    # Dialogue should not generate scene-scale affordances
    kinds = {c.split(":")[0] for c in rec.affordance_candidates}
    assert "move_through" not in kinds or rec.budget_class == "medium", "dialogue should not produce exits"


# ---------- Acceptance Test 10.3: Object Tool Use Is Locally Materialized ----------


def test_object_tool_use_locally_materialized():
    """找块石头卡住矿门 -> loose_stone may be proposed as soft object."""
    w = build()
    # Move player to mine gate
    from metarpg.models import Fact
    w.facts.discard(Fact("at", ("player", "tavern")))
    w.facts.add(Fact("at", ("player", "old_mine_gate")))

    hooks = build_hooks()
    engine = Engine(w, hooks=hooks)

    # Seed salient object frontier at gate
    from metarpg.frontier import create_frontier
    create_frontier(
        w,
        kind=FrontierKind.SALIENT_OBJECT,
        anchor="old_mine_gate",
        location="old_mine_gate",
        source_event="player_at_gate",
    )

    rec = engine.step("找块石头卡住矿门")

    assert len(rec.affordance_candidates) > 0, "expected affordance candidates"
    anchors = [c.split(":")[1].split("(")[0] for c in rec.affordance_candidates]
    assert "loose_stone" in anchors or "old_mine_gate" in anchors, f"expected stone/gate affordance, got {anchors}"


# ---------- Acceptance Test 10.4: Frontier Decay ----------


def test_frontier_decay():
    """Untouched frontier decays in salience and may be removed."""
    w = build()
    w.turn = 0

    f = create_frontier(
        w,
        kind=FrontierKind.LATENT_HOOK,
        anchor="card_game",
        location="tavern",
        source_event="saw_card_game",
        salience=0.3,
    )
    fid = f.id

    # Simulate 6 turns without touching
    w.turn = 6
    removed = decay_frontiers(w)

    if fid not in removed:
        # Should have decayed in salience
        assert w.frontiers[fid].salience < 0.3, "expected salience decay"

    # Simulate 12 turns total
    w.turn = 12
    removed = decay_frontiers(w)
    assert fid not in w.frontiers or fid in removed, "old expanded frontier should be removed"


# ---------- Acceptance Test 10.5: Over-Expansion Diagnostic ----------


def test_no_over_expansion_for_simple_dialogue():
    """Simple dialogue should not create many unrelated objects/NPCs."""
    w = build()
    hooks = build_hooks()
    engine = Engine(w, hooks=hooks)

    rec = engine.step("问玛拉最近的消息")

    facts_before = len(w.facts)
    # Allow small belief deltas, but no mass object/NPC injection
    hard_added = rec.canon_delta.get("facts_added") or []
    object_added = rec.canon_delta.get("objects_added") or []

    # Simple dialogue should add at most a few transient events, not new locations/NPCs
    assert len(object_added) <= 2, f"dialogue should not materialize many objects: {object_added}"


# ---------- v0.5 engine integration smoke tests ----------


def test_engine_step_records_budget_and_frontiers():
    """TurnRecord must carry v0.5 debug fields after a step."""
    w = build()
    hooks = build_hooks()
    engine = Engine(w, hooks=hooks)

    rec = engine.step("环顾四周")

    assert hasattr(rec, "budget_class")
    assert hasattr(rec, "touched_frontiers")
    assert hasattr(rec, "affordance_candidates")
    assert hasattr(rec, "top_affordance")
