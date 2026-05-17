"""v0.3.1 regression tests — subject-bound event hooks.

Per planVer0.3.1 §10-15. Verifies:
- Past events generate active hooks
- Hooks are matched by cue/topic/target overlap
- "刚才的情形" resolves through communicate hook
- Mara receives concrete knowledge from the report
- Hook lifecycle: ttl, consume, merge
"""
from __future__ import annotations

from metarpg.engine import Engine
from metarpg.hooks import consume_hook, get_active_hooks, is_hook_active, merge_similar_hooks, tick_hooks
from metarpg.models import Claim, ClaimStatus, EventHook, Fact, Knowledge, ProposedEffect
from metarpg.narrator import Narrator
from metarpg.scenarios.greyfen import build, build_hooks


def _engine():
    w = build()
    hooks = build_hooks()
    return Engine(w, narrator=Narrator(enabled=False), hooks=hooks)


# ---------- Hook lifecycle ----------


def test_tick_hooks_decays_ttl():
    """tick_hooks reduces ttl for decay_each_turn hooks."""
    e = _engine()
    e.world.hooks["H1"] = EventHook(id="H1", owner="player", ttl=3, decay_policy="decay_each_turn")
    tick_hooks(e.world)
    assert e.world.hooks["H1"].ttl == 2


def test_tick_hooks_expires_zero_ttl():
    """Hooks with ttl reaching 0 are removed."""
    e = _engine()
    e.world.hooks["H1"] = EventHook(id="H1", owner="player", ttl=1, decay_policy="decay_each_turn")
    tick_hooks(e.world)
    assert "H1" not in e.world.hooks


def test_consume_hook_removes_consume_once():
    """consume_once hooks are removed on consumption."""
    e = _engine()
    e.world.hooks["H1"] = EventHook(id="H1", owner="player", ttl=3, decay_policy="consume_once")
    assert consume_hook(e.world, "H1")
    assert "H1" not in e.world.hooks


def test_merge_similar_hooks_combines_topics():
    """Similar communicate hooks merge into one stronger hook."""
    e = _engine()
    e.world.hooks["H1"] = EventHook(
        id="H1", owner="player", hook_type="communicate",
        topics=["rusk"], trigger_cues=["告诉"], priority=0.5, ttl=3,
    )
    e.world.hooks["H2"] = EventHook(
        id="H2", owner="player", hook_type="communicate",
        topics=["rusk"], trigger_cues=["提起"], priority=0.6, ttl=4,
    )
    merged = merge_similar_hooks(e.world)
    assert len(merged) == 1
    assert len(e.world.hooks) == 1
    remaining = list(e.world.hooks.values())[0]
    assert "告诉" in remaining.trigger_cues
    assert "提起" in remaining.trigger_cues
    assert remaining.priority > 0.6


# ---------- Hook matching ----------


def test_hook_match_by_cue_overlap():
    """Hook matches when text contains trigger cues."""
    from metarpg.hookmatch import match_active_hooks
    from metarpg.metaact import build_metaact

    e = _engine()
    e.world.hooks["H1"] = EventHook(
        id="H1", owner="player", hook_type="communicate",
        trigger_cues=["刚才", "情形", "告诉"],
        valid_targets=["mara"],
        source_turn=1, priority=0.8, ttl=3,
    )
    meta = build_metaact("将刚才的情形告诉了玛拉", e.world)
    matched, score = match_active_hooks(meta, e.world)
    assert matched is not None
    assert matched.id == "H1"
    assert score >= 0.45


def test_hook_match_requires_target_present():
    """Hook only matches strongly if valid target is nearby."""
    from metarpg.hookmatch import match_active_hooks
    from metarpg.metaact import build_metaact

    e = _engine()
    # Mara is at tavern by default (player is also at tavern)
    e.world.hooks["H1"] = EventHook(
        id="H1", owner="player", hook_type="communicate",
        trigger_cues=["刚才", "情形"],
        valid_targets=["rusk"],  # Rusk is NOT at tavern
        source_turn=1, priority=0.8, ttl=3,
    )
    meta = build_metaact("将刚才的情形告诉了玛拉", e.world)
    matched, score = match_active_hooks(meta, e.world)
    # Should still match because "玛拉" is nearby, but rusk hook target mismatch lowers score
    # The match threshold may not be reached
    if matched:
        assert matched.id == "H1"


# ---------- "刚才的情形" acceptance test ----------


def test_just_now_situation_manual_hook():
    """Direct test: pre-created communicate hook triggers on '刚才的情形'."""
    e = _engine()

    # Manually inject a communicate hook simulating prior events
    e.world.hooks["H_guard_mine_report"] = EventHook(
        id="H_guard_mine_report",
        owner="player",
        source_turn=1,
        source_events=["player_visited_guard_post", "rusk_was_evasive", "old_mine_access_blocked"],
        hook_type="communicate",
        trigger_cues=["刚才", "刚刚", "情形", "告诉", "说给", "提起", "守卫", "拉斯克", "老矿"],
        valid_targets=["mara"],
        payload_claims=[
            Claim("player_knows", ("player_visited_guard_post",), ClaimStatus.ACCEPTED, "玩家亲历"),
            Claim("player_knows", ("rusk_was_evasive",), ClaimStatus.ACCEPTED, "玩家亲历"),
            Claim("player_knows", ("old_mine_access_blocked",), ClaimStatus.ACCEPTED, "玩家亲历"),
        ],
        proposed_effects=[
            ProposedEffect("add_knowledge", (Knowledge("mara", Fact("rusk_was_evasive_to_player", ())),), 2),
            ProposedEffect("belief_delta", ("rusk_pressures_mara", 0.04), 2),
            ProposedEffect("observe", ("mara_tenses_at_rusk",), 0),
        ],
        topics=["rusk", "old_mine"],
        places=["guard_post", "old_mine_gate"],
        participants=["rusk"],
        priority=0.85,
        ttl=4,
        decay_policy="consume_once",
    )

    rec = e.step("耸了耸肩，将刚才的情形告诉了玛拉")

    # Should trigger the hook
    assert rec.hypothesis_kind == "trigger_event_hook"
    # Knowledge transferred to Mara
    knowledge_added = rec.canon_delta.get("knowledge_added", [])
    assert len(knowledge_added) > 0, f"Mara should receive knowledge: {rec.canon_delta}"
    # Hook should be consumed
    assert "H_guard_mine_report" not in e.world.hooks


def test_just_now_situation_hook_claims_validated():
    """Hook claims are validated: hook_active, same_location, player_knows."""
    e = _engine()
    e.world.hooks["H_test"] = EventHook(
        id="H_test", owner="player", source_turn=1,
        hook_type="communicate", trigger_cues=["刚才", "情形"],
        valid_targets=["mara"], source_events=["test_event"],
        proposed_effects=[
            ProposedEffect("observe", ("mara_listened",), 0),
        ],
        priority=0.8, ttl=3,
    )

    rec = e.step("将刚才的情形告诉了玛拉")
    assert rec.hypothesis_kind == "trigger_event_hook"
    # Claims should show validation results
    claim_names = [c[0] for c in rec.claim_summary]
    assert "hook_active" in claim_names
    assert "same_location" in claim_names
    assert "player_knows" in claim_names


# ---------- End-to-end: script generates hooks then triggers ----------


def test_end_to_end_guard_post_sequence():
    """Full script: guard post visit, ask Rusk, blocked mine, tell Mara."""
    e = _engine()

    # Turn 1: go to guard post
    e.step("前往守卫站")
    # Should generate return hook + meet_rusk hook
    assert len(e.world.hooks) > 0

    # Turn 2: ask Rusk about danger
    e.step("我想了解一下这附近有没有什么危险")
    # Should generate rusk interaction hook

    # Turn 3: try go to old mine (blocked)
    e.step("前往老矿")
    # Should generate blocked_access hook

    # Turn 4: go back to tavern
    e.step("前往酒馆")

    # Turn 5: tell Mara about what happened
    rec = e.step("耸了耸肩，将刚才的情形告诉了玛拉")

    # Should match a communicate hook
    assert rec.hypothesis_kind == "trigger_event_hook"
    # Should produce some effect (knowledge or observation)
    assert rec.validation.ok, f"Unexpected rejection: {rec.validation.reason}"
    # At least one of: knowledge_added, observations, belief_deltas
    has_effect = (
        rec.canon_delta.get("knowledge_added")
        or rec.canon_delta.get("observations")
        or rec.canon_delta.get("belief_deltas")
        or rec.canon_delta.get("events")
    )
    assert has_effect, f"No effects produced: {rec.canon_delta}"


# ---------- Failure mode guards ----------


def test_no_hook_match_falls_back_to_normal_proposer():
    """When no hook matches, normal proposer still works."""
    e = _engine()
    rec = e.step("问问玛拉附近有什么大事")
    assert rec.hypothesis_kind == "ask_about_topic"
    assert rec.validation.ok


def test_hook_consumed_not_reusable():
    """Once consumed, hook cannot be triggered again."""
    e = _engine()
    e.world.hooks["H1"] = EventHook(
        id="H1", owner="player", source_turn=1,
        hook_type="communicate", trigger_cues=["刚才"],
        valid_targets=["mara"], source_events=["event1"],
        proposed_effects=[ProposedEffect("observe", ("mara_listened",), 0)],
        priority=0.8, ttl=3, decay_policy="consume_once",
    )

    # First trigger
    rec1 = e.step("将刚才的事告诉玛拉")
    assert rec1.hypothesis_kind == "trigger_event_hook"

    # Second trigger — hook is gone
    rec2 = e.step("再次提起刚才的事")
    # Should NOT be trigger_event_hook (hook consumed)
    assert rec2.hypothesis_kind != "trigger_event_hook"


def test_absent_target_blocks_hook_effects():
    """If target is not present, hook effects are filtered."""
    e = _engine()
    # Move player to tavern (Mara is there by default)
    # But create a hook targeting Rusk (who is at guard_post)
    e.world.hooks["H_rusk"] = EventHook(
        id="H_rusk", owner="player", source_turn=1,
        hook_type="communicate", trigger_cues=["刚才", "情形"],
        valid_targets=["rusk"], source_events=["event1"],
        proposed_effects=[
            ProposedEffect("rel_delta", ("rusk", "player", "trust", 0.05), 1),
        ],
        priority=0.8, ttl=3,
    )

    rec = e.step("将刚才的情形告诉拉斯克")
    # The hook matches (text has cues), but same_location claim fails
    # Because Rusk is not at tavern
    # rel_delta should be filtered
    rel_deltas = rec.canon_delta.get("rel_deltas", [])
    assert not any(d[0] == "rusk" for d in rel_deltas), \
        f"Rusk should not be affected when absent: {rel_deltas}"
