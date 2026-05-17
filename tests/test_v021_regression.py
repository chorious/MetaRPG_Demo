"""v0.2.1 regression tests — admission control tightened.

Covers review_v0.2.1.md:
- Movement produces hard state delta
- Sealed location cannot be directly reached
- Unknown target does not become canon event
- Arrival requires fact delta
"""
from __future__ import annotations

from metarpg.engine import Engine
from metarpg.models import Fact
from metarpg.narrator import Narrator
from metarpg.scenarios.greyfen import build, build_hooks


def _engine():
    w = build()
    hooks = build_hooks()
    return Engine(w, narrator=Narrator(enabled=False), hooks=hooks)


def test_movement_changes_player_location():
    """前往守卫站 must move player to guard_post."""
    e = _engine()
    rec = e.step("前往守卫站")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "guard_post")) in e.world.facts
    assert Fact("at", ("player", "tavern")) not in e.world.facts


def test_movement_updates_nearby_npcs():
    """After moving, nearby NPCs should reflect new location."""
    e = _engine()
    e.step("前往守卫站")
    loc = _player_location(e.world)
    assert loc == "guard_post"
    nearby = _nearby_npcs(e.world)
    assert "rusk" in nearby
    assert "mara" not in nearby


def test_sealed_mine_is_blocked():
    """去老矿 must be rejected because old_mine is sealed."""
    e = _engine()
    rec = e.step("去老矿")
    assert not rec.validation.ok
    assert Fact("at", ("player", "old_mine")) not in e.world.facts
    assert "old_mine" not in _player_location(e.world)


def test_mine_gate_is_reachable():
    """去矿口 must succeed."""
    e = _engine()
    rec = e.step("去矿口")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "old_mine_gate")) in e.world.facts


def test_unknown_target_does_not_become_canon_event():
    """自由输入不在白名单的目标，Path A 应降级给 MetaAct。"""
    e = _engine()
    rec = e.step("看了一眼角落")
    events = rec.canon_delta.get("events", [])
    for ev in events:
        assert "了一眼" not in str(ev)


def test_ambiguous_input_produces_transient_event():
    """无法归类的输入产生 transient_event，不进 hard canon facts。"""
    e = _engine()
    rec = e.step("随便说一句无法归类的话")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "ambiguous_social_act"


def test_free_form_ask_local_news():
    """问问玛拉附近有什么大事 -> ask_about_topic, accepted."""
    e = _engine()
    rec = e.step("问问玛拉附近有什么大事")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "ask_about_topic"


def test_free_form_order_ale():
    """Order drink hypothesis accepted."""
    e = _engine()
    rec = e.step('耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"')
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "order_drink"


def test_free_form_complain():
    """Complain hypothesis accepted."""
    e = _engine()
    rec = e.step("怎么回事，你们酒馆甚至没有酒么！")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "complain_about_service"


def test_old_commands_still_work():
    """Backward compatibility: well-formed commands still work."""
    e = _engine()
    rec = e.step("ask Mara about the mine")
    assert rec.validation.ok
    rec = e.step("go to guard post")
    assert rec.validation.ok
    rec = e.step("observe Mara")
    assert rec.validation.ok
    # Go back to tavern before helping Mara
    rec = e.step("go to tavern")
    assert rec.validation.ok
    rec = e.step("help Mara")
    assert rec.validation.ok


def test_listen_combo_still_works():
    """Rusk+Mara listen combo still updates beliefs."""
    e = _engine()
    e.world.facts.discard(Fact("at", ("rusk", "guard_post")))
    e.world.facts.add(Fact("at", ("rusk", "tavern")))
    before = e.world.beliefs["H3"].prob
    rec = e.step("listen to Rusk and Mara")
    assert rec.validation.ok
    after = e.world.beliefs["H3"].prob
    assert after > before


def test_retrodict_canonizes_when_threshold_crossed():
    """High-confidence belief triggers retrodiction."""
    e = _engine()
    e.world.beliefs["H1"].prob = 0.75  # below threshold, confront pushes it over
    rec = e.step("质问玛拉关于矿场")
    assert rec.validation.ok
    assert rec.retropath_status == "canonized"
    canon_strs = {str(f) for f in e.world.facts}
    assert any("saw(mara" in s for s in canon_strs)


def test_free_form_ambiguous_near_npc():
    """Ambiguous input near NPC produces social act, not unparseable."""
    e = _engine()
    rec = e.step("你这里的影子看起来很旧")
    assert rec.validation.ok
    assert rec.hypothesis_kind == "ambiguous_social_act"


def test_chinese_movement():
    """中文移动命令工作正常。"""
    e = _engine()
    rec = e.step("去守卫站")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "guard_post")) in e.world.facts


def test_chinese_ask():
    """中文询问命令工作正常。"""
    e = _engine()
    rec = e.step("问玛拉关于矿场")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "ask_about_topic"


def test_chinese_confront():
    """中文质问命令工作正常。"""
    e = _engine()
    rec = e.step("质问玛拉关于矿场")
    assert rec.validation.ok, rec.validation.reason
    assert rec.hypothesis_kind == "confront_about_topic"


def test_chinese_observe():
    """中文观察命令工作正常。"""
    e = _engine()
    rec = e.step("观察玛拉")
    assert rec.validation.ok, rec.validation.reason


def test_chinese_help():
    """中文帮助命令工作正常。"""
    e = _engine()
    rec = e.step("帮助玛拉")
    assert rec.validation.ok, rec.validation.reason


def test_chinese_listen():
    """中文偷听命令工作正常。"""
    e = _engine()
    e.world.facts.discard(Fact("at", ("rusk", "guard_post")))
    e.world.facts.add(Fact("at", ("rusk", "tavern")))
    rec = e.step("听拉斯克和玛拉")
    assert rec.validation.ok, rec.validation.reason


def test_chinese_sneak():
    """中文潜入命令工作正常（需要入口已开启）。"""
    e = _engine()
    e.world.facts.add(Fact("at", ("player", "old_mine_gate")))
    e.world.facts.add(Fact("opened", ("old_mine",)))  # unseal for this test
    rec = e.step("潜入老矿")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "old_mine")) in e.world.facts


def test_go_to_tavern_from_guard_post():
    """从守卫站返回酒馆。"""
    e = _engine()
    e.step("前往守卫站")
    rec = e.step("去酒馆")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "tavern")) in e.world.facts
    assert Fact("at", ("player", "guard_post")) not in e.world.facts


def test_go_to_cellar():
    """去地窖。"""
    e = _engine()
    rec = e.step("去地窖")
    assert rec.validation.ok, rec.validation.reason
    assert Fact("at", ("player", "mara_cellar")) in e.world.facts


# ---------- helpers ----------


def _player_location(world) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _nearby_npcs(world) -> list[str]:
    loc = _player_location(world)
    out: list[str] = []
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if entity != "player" and place == loc and entity in world.npcs:
                out.append(entity)
    return out
