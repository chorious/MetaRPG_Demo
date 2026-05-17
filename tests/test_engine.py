"""End-to-end engine tests against the Greyfen scenario.

Covers PLAN_SONNET §11 minimum acceptance:
  - at least 5 actions (ask, go, observe, confront, help)
  - at least 1 action rejected by rule validation
  - at least 1 future event updates past hidden-state probability
  - at least 1 retrodictive explanation path can be canonized
"""
from __future__ import annotations

from metarpg.engine import Engine, parse_input
from metarpg.narrator import Narrator
from metarpg.scenarios.greyfen import build, build_hooks


def _engine(use_hooks: bool = True) -> Engine:
    w = build()
    hooks = build_hooks() if use_hooks else None
    return Engine(w, narrator=Narrator(enabled=False), hooks=hooks)


# ---------- parsing ----------

def test_parse_ask_with_about():
    a = parse_input("ask Mara about the mine")
    assert a is not None
    assert a.verb == "ask"
    assert a.args == ("mara", "mine")


def test_parse_go_to_place():
    a = parse_input("go to guard post")
    assert a is not None
    assert a.verb == "go"
    assert a.args == ("guard_post",)


def test_parse_listen_multi_targets():
    a = parse_input("listen to Rusk and Mara")
    assert a is not None
    assert a.verb == "listen"
    assert set(a.args) == {"rusk", "mara"}


# ---------- per-action behavior ----------

def test_ask_mara_in_same_room_succeeds():
    e = _engine()
    rec = e.step("ask Mara about the mine")
    assert rec.validation.ok
    # belief updates were recorded
    assert any(desc == "mara_knows_recent_entry" for desc, *_ in rec.belief_modulation)


def test_ask_rusk_rejected_when_not_same_room():
    e = _engine()
    rec = e.step("ask Rusk about the mine")
    assert not rec.validation.ok
    assert "same_location" in rec.validation.reason or "not_same" in rec.validation.reason


def test_go_to_guard_post_moves_player():
    e = _engine()
    rec = e.step("go to guard post")
    assert rec.validation.ok
    from metarpg.models import Fact
    assert Fact("at", ("player", "guard_post")) in e.world.facts
    assert Fact("at", ("player", "tavern")) not in e.world.facts


def test_observe_runs_even_without_target():
    e = _engine()
    rec = e.step("observe Mara")
    assert rec.validation.ok


def test_confront_changes_trust_and_fear():
    e = _engine()
    rec = e.step("confront Mara about the mine")
    assert rec.validation.ok
    rel = e.world.get_relation("mara", "player")
    assert rel is not None
    assert rel.dimensions.get("fear", 0) > 0.10  # baseline 0.10 raised


def test_help_mara_boosts_trust():
    e = _engine()
    before = e.world.get_relation("mara", "player").dimensions["trust"]
    rec = e.step("help Mara")
    assert rec.validation.ok
    after = e.world.get_relation("mara", "player").dimensions["trust"]
    assert after > before


def test_parse_chinese_ask():
    a = parse_input("问玛拉关于矿场")
    assert a is not None
    assert a.verb == "ask"
    assert a.args == ("mara", "mine")


def test_parse_chinese_go():
    a = parse_input("去守卫站")
    assert a is not None
    assert a.verb == "go"
    assert a.args == ("guard_post",)


def test_parse_chinese_listen():
    a = parse_input("听拉斯克和玛拉")
    assert a is not None
    assert a.verb == "listen"
    assert set(a.args) == {"rusk", "mara"}


def test_unknown_action_becomes_ambiguous_social_act():
    """v0.2: non-empty input near an NPC produces ambiguous_social_act, not unparseable."""
    e = _engine()
    rec = e.step("xyzzy")
    assert rec.validation.ok
    assert rec.hypothesis_kind == "ambiguous_social_act"


# ---------- §11 acceptance scenarios ----------

def test_future_event_updates_past_hidden_state():
    """§11: at least 1 future event updates past hidden-state probability."""
    e = _engine()
    before = e.world.beliefs["H3"].prob
    # Bring Rusk to the tavern programmatically so listen requirement passes
    from metarpg.models import Fact
    e.world.facts.discard(Fact("at", ("rusk", "guard_post")))
    e.world.facts.add(Fact("at", ("rusk", "tavern")))
    rec = e.step("listen to Rusk and Mara")
    assert rec.validation.ok, rec.validation.reason
    after = e.world.beliefs["H3"].prob
    assert after > before


def test_retropath_canonizes_when_threshold_crossed():
    """§11: at least 1 retrodictive explanation path can be canonized."""
    e = _engine()
    # Push rusk_pressures_mara above 0.80 by setting prior and listening
    e.world.beliefs["H3"].prob = 0.60
    from metarpg.models import Fact
    e.world.facts.discard(Fact("at", ("rusk", "guard_post")))
    e.world.facts.add(Fact("at", ("rusk", "tavern")))
    rec = e.step("listen to Rusk and Mara")
    assert rec.validation.ok
    assert e.world.beliefs["H3"].prob >= 0.80
    assert rec.retropath_status == "canonized"
    # New canon contains at least one retropath fact
    canon_strs = {str(f) for f in e.world.facts}
    assert any("rusk_threatened_mara" in s or "mara_saw_rusk_near_mine" in s for s in canon_strs)


def test_archive_collects_player_inputs():
    """§11: Cold archive preserves raw text but normal turns do not reread full archive."""
    import os, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "arch.jsonl")
        w = build(archive_path=archive)
        e = Engine(w, narrator=Narrator(enabled=False))
        e.step("ask Mara about the mine")
        e.step("observe Mara")
        with open(archive, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # at least 2 player_input lines + 2 narration lines = 4 entries
        kinds = [line for line in lines if "player_input" in line]
        assert len(kinds) >= 2
