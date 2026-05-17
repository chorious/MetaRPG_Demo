"""DSL round-trip and parser tests."""
from __future__ import annotations

from metarpg import dsl
from metarpg.models import (
    AvailableAction,
    Belief,
    Effect,
    Fact,
    Knowledge,
    LocalSlice,
    Motif,
    Patch,
    Relation,
    Retropath,
)


def test_parse_fact():
    f = dsl.parse_fact("at(player,tavern)")
    assert f == Fact("at", ("player", "tavern"))


def test_layer_line_fact():
    obj = dsl.parse_layer_line("@FACT sealed(old_mine)")
    assert obj == Fact("sealed", ("old_mine",))


def test_layer_line_knowledge():
    k = dsl.parse_layer_line("@KNOW mara knows sealed(old_mine)")
    assert k == Knowledge("mara", Fact("sealed", ("old_mine",)))


def test_layer_line_relation():
    r = dsl.parse_layer_line("@REL mara->player trust=.18 fear=.10 curiosity=.35")
    assert r.from_agent == "mara" and r.to_agent == "player"
    assert abs(r.dimensions["trust"] - 0.18) < 1e-9
    assert abs(r.dimensions["curiosity"] - 0.35) < 1e-9


def test_layer_line_motif():
    m = dsl.parse_layer_line("@MOTIF forbidden_place(old_mine) lure=.62 danger=.48")
    assert m.name == "forbidden_place"
    assert m.args == ("old_mine",)
    assert abs(m.params["lure"] - 0.62) < 1e-9


def test_layer_line_frontier():
    fs = dsl.parse_layer_line(
        "@FRONTIER ask(mara,old_mine) | sneak(old_mine_gate) | confront(rusk,mara)"
    )
    assert len(fs) == 3
    assert fs[0].verb == "ask" and fs[0].args == ("mara", "old_mine")


def test_layer_line_belief():
    b = dsl.parse_layer_line("@BELIEF H1 mara_knows_recent_entry p=.45")
    assert b == Belief("H1", "mara_knows_recent_entry", 0.45)


def test_render_slice_roundtrip():
    sl = LocalSlice(
        touched={"player", "mara"},
        facts=[Fact("at", ("player", "tavern"))],
        knowledge=[Knowledge("mara", Fact("sealed", ("old_mine",)))],
        relations=[Relation("mara", "player", {"trust": 0.18})],
        motifs=[Motif("forbidden_place", ("old_mine",), {"lure": 0.62})],
        beliefs=[Belief("H1", "mara_knows_recent_entry", 0.45)],
        frontier=[AvailableAction("ask", ("mara", "old_mine"))],
    )
    text = dsl.render_slice(sl)
    assert "@FACT at(player,tavern)" in text
    assert "@KNOW mara knows sealed(old_mine)" in text
    assert "@REL mara->player trust=.18" in text
    assert "@MOTIF forbidden_place(old_mine) lure=.62" in text
    assert "@BELIEF H1 mara_knows_recent_entry p=.45" in text
    assert "@FRONTIER ask(mara,old_mine)" in text


def test_render_patch_matches_planspec():
    p = Patch(
        intent="ask(player,mara,old_mine_recent_activity)",
        requirements=["same_location(player,mara)"],
        effects=[
            Effect("event", ("player_asked_mara_about_mine",)),
            Effect("observe", ("mara_evasive_about_mine",)),
            Effect("rel_delta", ("mara", "player", "trust", 0.04)),
            Effect("belief_delta", ("mara_knows_recent_entry", 0.10)),
        ],
    )
    text = dsl.render_patch(p)
    assert "TRY ask(player,mara,old_mine_recent_activity)" in text
    assert "REQUIRES same_location(player,mara)" in text
    assert "EFFECT rel_delta(mara,player,trust,+.04)" in text
    assert "EFFECT belief_delta(mara_knows_recent_entry,+.10)" in text


def test_render_retropath():
    rp = Retropath(
        target="rusk_pressures_mara",
        causes=[
            Fact("mara_saw_rusk_near_mine", ("day_minus_2",)),
            Fact("rusk_threatened_mara", ("day_minus_1",)),
        ],
        explains=["mara_evasive_about_mine"],
    )
    text = dsl.render_retropath(rp)
    assert text.splitlines()[0] == "RETROPATH rusk_pressures_mara"
    assert "CAUSE mara_saw_rusk_near_mine(day_minus_2)" in text
    assert "EXPLAINS mara_evasive_about_mine" in text


def test_parse_patch_roundtrip():
    src = (
        "TRY ask(player,mara,mine)\n"
        "REQUIRES same_location(player,mara)\n"
        "EFFECT event(asked_mara)\n"
        "EFFECT rel_delta(mara,player,trust,+.04)\n"
    )
    p = dsl.parse_patch(src)
    assert p.intent == "ask(player,mara,mine)"
    assert p.requirements == ["same_location(player,mara)"]
    assert p.effects[0].kind == "event"
    assert p.effects[1].kind == "rel_delta"
    assert p.effects[1].payload == ("mara", "player", "trust", 0.04)
