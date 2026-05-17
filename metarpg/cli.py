"""Terminal REPL for MetaRPG v0.1 — CanonWorld-inspired UI.

参考 CanonWorld_Demo 的交互设计:
  - 每回合前显示状态面板(地点/附近人/可去地点/关键信念)
  - 默认 compact 模式只显示叙事+关键变化
  - /debug 切换显示完整技术细节
  - 启动时选择模式
  - 每回合写入 session_*.md 交互文档
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from . import dsl
from .engine import Engine, TurnRecord
from .models import Fact, WorldState
from .narrator import Narrator
from .scenario_hooks import ScenarioHooks
from .session_logger import SessionLogger


BAR_WIDTH = 40

_HELP_TEXT = """\
═══════════════════════════════════════
  命令 (中英双语)
═══════════════════════════════════════
  问 <人物> 关于 <话题>     — 询问
  去 <地点>                 — 移动
  看 <目标>                 — 观察
  质问 <人物> 关于 <话题>   — 质问
  帮 <人物>                 — 帮助
  听 <人物> 和 <人物>       — 偷听
  潜入 <地点>               — 潜入

  调试: /debug  /matrix  /canon  /beliefs  /archive  /frontier  /affordance
  缓存: /reset
  退出: /quit  /exit
═══════════════════════════════════════
"""

# Chinese name maps for the UI
_LOC_CN: dict[str, str] = {
    "tavern": "酒馆",
    "guard_post": "守卫站",
    "old_mine": "老矿",
    "old_mine_gate": "矿口",
    "mara_cellar": "地窖",
}
_NPC_CN: dict[str, str] = {
    "mara": "玛拉",
    "rusk": "拉斯克",
    "iven": "艾文",
}
_BELIEF_DESC_CN: dict[str, str] = {
    "mara_knows_recent_entry": "玛拉知道最近的入口",
    "mara_entered_mine": "玛拉进过矿",
    "rusk_pressures_mara": "拉斯克在施压玛拉",
    "iven_alive_in_mine": "艾文活着在矿里",
    "iven_dead_and_hidden": "艾文已死并被藏起",
    "mara_ignorant_about_mine": "玛拉对矿场一无所知",
}
_EVENT_DESC_CN: dict[str, str] = {
    "player_asked_mara_about_mine": "你向玛拉问起矿场",
    "player_asked_rusk_about_mine": "你向拉斯克问起矿场",
    "player_asked_mara_about_iven": "你向玛拉问起艾文",
    "player_asked_mara_about_local_news": "你向玛拉打听附近的消息",
    "player_asked_someone_about_something": "你向某人问起某事",
    "player_confronted_mara_about_mine": "你质问玛拉关于矿场",
    "player_confronted_someone_about_something": "你质问某人",
    "player_observed_mara": "你观察了玛拉",
    "player_observed_scene": "你观察了周围",
    "player_helped_mara": "你帮助了玛拉",
    "player_listened_to_rusk_and_mara": "你偷听到拉斯克与玛拉的对话",
    "player_listened_to_silence": "你侧耳倾听，只听到寂静",
    "player_arrived_at_guard_post": "你抵达了守卫站",
    "player_arrived_at_tavern": "你回到酒馆",
    "player_sneaked_into_old_mine": "你潜入老矿",
    "player_ordered_ale_from_mara": "你向玛拉要了一杯麦芽啤酒",
    "social_signal_player_mara_ordinary_customer_request": "玛拉把你当作普通顾客",
    "player_complained_to_mara_about_no_service": "你向玛拉抱怨酒馆的服务",
    "social_signal_player_mara_irritated_customer": "玛拉察觉到你的不满",
    "player_spoke_unclearly_to_mara": "你对玛拉说了些含糊的话",
    "mara_acknowledged_or_ignored_player": "玛拉点了点头",
    "player_made_unclear_gesture": "你做了个不明所以的动作",
    "mara_evasive_about_mine": "玛拉对矿场话题闪烁其词",
    "mara_evasive_about_iven": "玛拉对艾文话题避而不答",
    "mara_defensive_about_mine": "玛拉对矿场话题充满防御",
    "rusk_evasive_about_mine": "拉斯克对矿场话题避而不谈",
    "rusk_warning_mara_about_outsiders": "拉斯克警告玛拉不要对局外人透露",
    "mara_responded_to_mine": "玛拉回应了矿场的话题",
    "mara_responded_to_topic": "玛拉回应了你的话题",
    "mara_responded_to_something": "玛拉有所回应",
}


def _cn_loc(loc: str) -> str:
    return _LOC_CN.get(loc, loc)


def _cn_npc(npc: str) -> str:
    return _NPC_CN.get(npc, npc)


def _cn_belief(desc: str) -> str:
    return _BELIEF_DESC_CN.get(desc, desc)


def _cn_event(ev: str) -> str:
    return _EVENT_DESC_CN.get(ev, ev)


def _current_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return "未知"


def _nearby_npcs(world: WorldState) -> list[str]:
    loc = _current_location(world)
    out: list[str] = []
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if entity != "player" and place == loc and entity in world.npcs:
                out.append(entity)
    return out


def _available_locations(world: WorldState) -> list[str]:
    cur = _current_location(world)
    return sorted([l for l in world.locations if l != cur])


def _key_beliefs(world: WorldState) -> list[tuple[str, float]]:
    items = [(b.description, b.prob) for b in world.beliefs.values() if b.prob >= 0.30]
    items.sort(key=lambda x: -x[1])
    return items


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(prog="metarpg")
    parser.add_argument("--scenario", default="greyfen", help="scenario module name")
    parser.add_argument("--no-llm", action="store_true", help="disable LLM narrator")
    parser.add_argument("--debug", action="store_true", help="show full technical output")
    parser.add_argument(
        "--runtime",
        default=os.path.join(_project_root(), "runtime"),
        help="runtime dir for archive + canon log + session log",
    )
    parser.add_argument(
        "--env",
        default=os.path.join(_project_root(), "set.env"),
        help="path to set.env",
    )
    parser.add_argument(
        "--script",
        default=None,
        help="optional path to a newline-separated script of player inputs",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="clear cold archive and canon log before starting",
    )
    args = parser.parse_args(argv)

    # Handle cache clearing
    _maybe_clear_cache(args.runtime, args.scenario, force=args.reset, interactive=not args.script)

    world, hooks = _load_scenario(args.scenario, args.runtime)

    # Mode selection
    mode = "llm"
    if args.no_llm:
        mode = "mock"
    elif not args.script:
        print("\n" + "═" * BAR_WIDTH)
        print("        《灰井之谜》")
        print("        MetaRPG v0.1 演示版")
        print("═" * BAR_WIDTH)
        print("\n选择模式：")
        print("  1. 纯模板 — 确定性叙事（最快、零延迟）")
        print("  2. LLM润色 — 本地模型生成叙事（默认）")
        try:
            choice = input("\n模式 [2]: ").strip()
            if choice == "1":
                mode = "mock"
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

    narrator = Narrator(env_path=args.env, enabled=(mode == "llm"))
    engine = Engine(world, narrator=narrator, hooks=hooks)

    # Session logger
    from datetime import datetime
    session_path = os.path.join(
        args.runtime, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    session = SessionLogger(session_path, scenario=args.scenario, mode=mode_desc(mode))

    print(f"\n当前模式：{mode_desc(mode)}")
    print(f"交互记录：{session_path}")
    print("\n你来到灰井村。老矿被封印着，但最近有人进去了。")
    print("玛拉在酒馆里闪烁其词，拉斯克在守卫站虎视眈眈。")
    print("艾文已经失踪三天。\n")
    print("操作说明：直接输入想做的事，输入 /help 查看命令。")
    print("═" * BAR_WIDTH)

    debug_mode = args.debug

    if args.script:
        return _run_script(engine, session, args.script, debug_mode)
    return _repl(engine, session, debug_mode)


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cache_paths(runtime_dir: str, scenario: str) -> list[str]:
    """Return list of cache files that can be cleared."""
    return [
        os.path.join(runtime_dir, f"cold_archive_{scenario}.jsonl"),
        os.path.join(runtime_dir, f"canon_{scenario}.log"),
    ]


def _maybe_clear_cache(runtime_dir: str, scenario: str, force: bool, interactive: bool) -> None:
    """Prompt to clear cache on restart, or clear immediately if --reset."""
    paths = _cache_paths(runtime_dir, scenario)
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return
    if force:
        for p in existing:
            os.remove(p)
        print("  [已清空缓存]")
        return
    if interactive:
        print(f"\n  检测到 {len(existing)} 个历史缓存文件。")
        try:
            choice = input("  是否清空重新开始？(y/N): ").strip().lower()
            if choice in ("y", "yes", "是"):
                for p in existing:
                    os.remove(p)
                print("  [已清空缓存]")
        except (EOFError, KeyboardInterrupt):
            pass


def _load_scenario(name: str, runtime_dir: str) -> tuple[WorldState, ScenarioHooks]:
    if name == "greyfen":
        from .scenarios.greyfen import build, build_hooks
    else:
        raise SystemExit(f"未知场景: {name}")
    os.makedirs(runtime_dir, exist_ok=True)
    archive_path = os.path.join(runtime_dir, f"cold_archive_{name}.jsonl")
    canon_log = os.path.join(runtime_dir, f"canon_{name}.log")
    # cold_archive and canon_log are append-only; do not delete on restart.
    return build(archive_path=archive_path, canon_log_path=canon_log), build_hooks()


def _repl(engine: Engine, session: SessionLogger, debug_mode: bool) -> int:
    while True:
        _print_status_panel(engine.world)
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n再见。")
            session.close()
            return 0
        if not line:
            continue
        if line.lower() in ("/quit", "/exit", "q", "quit", "退出"):
            print("\n\n你离开了灰井村。老矿的封印依然沉默。")
            session.close()
            return 0
        if line == "/help":
            print(_HELP_TEXT)
            continue
        if line == "/debug":
            debug_mode = not debug_mode
            print(f"  [调试模式: {'开启' if debug_mode else '关闭'}]")
            continue
        if line == "/matrix":
            print(_render_full_matrix(engine.world))
            continue
        if line == "/canon":
            for f in sorted(engine.world.facts, key=str):
                print(f"  @FACT {f}")
            continue
        if line == "/beliefs":
            for b in engine.world.beliefs.values():
                print(f"  {dsl.render_belief(b)}")
            continue
        if line == "/archive":
            _tail_archive(engine.world.archive_path)
            continue
        if line == "/frontier":
            print(_render_frontiers(engine.world))
            continue
        if line == "/affordance":
            print(_render_affordance_debug(engine.world))
            continue
        if line == "/reset":
            paths = _cache_paths(os.path.dirname(session.path), args.scenario)
            cleared = 0
            for p in paths:
                if os.path.exists(p):
                    os.remove(p)
                    cleared += 1
            print(f"  [已清空 {cleared} 个缓存文件]")
            continue

        rec = engine.step(line)
        if debug_mode:
            _print_turn_debug(rec)
        else:
            _print_turn_compact(rec)
        session.write_turn(rec, engine.world)
    return 0


def _run_script(engine: Engine, session: SessionLogger, path: str, debug_mode: bool) -> int:
    if not os.path.exists(path):
        print(f"脚本未找到: {path}", file=sys.stderr)
        return 2
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            _print_status_panel(engine.world)
            print(f"\n> {line}")
            rec = engine.step(line)
            if debug_mode:
                _print_turn_debug(rec)
            else:
                _print_turn_compact(rec)
            session.write_turn(rec, engine.world)
    session.close()
    return 0


# ---------- status panel ----------

def _print_status_panel(world: WorldState) -> None:
    loc = _current_location(world)
    nearby = _nearby_npcs(world)
    avail = _available_locations(world)
    beliefs = _key_beliefs(world)

    print("\n" + "─" * BAR_WIDTH)
    print(f"  地点：{_cn_loc(loc)}")

    if nearby:
        names = " ｜ ".join(_cn_npc(n) for n in nearby)
        print(f"  附近的人：{names}")
    else:
        print("  附近：空无一人")

    if avail:
        places = " ｜ ".join(_cn_loc(a) for a in avail)
        print(f"  可去：{places}")

    if beliefs:
        parts = []
        for desc, prob in beliefs[:4]:
            label = _cn_belief(desc)
            if prob >= 0.80:
                parts.append(f"{label} [{prob:.0%}]")
            else:
                parts.append(f"{label} ({prob:.0%})")
        print(f"  关键线索：{' ｜ '.join(parts)}")

    print("─" * BAR_WIDTH)


# ---------- compact turn output ----------

def _print_turn_compact(rec: TurnRecord) -> None:
    if not rec.validation.ok:
        reason = _humanize_rejection(rec.validation.reason)
        print(f"\n  [动作失败] {reason}")
        return

    # Narration (main)
    if rec.narration:
        print(f"\n  {rec.narration}")

    # Belief changes
    if rec.belief_modulation:
        print()
        for desc, raw, applied, prob in rec.belief_modulation:
            arrow = "↑" if applied >= 0 else "↓"
            label = _cn_belief(desc)
            if prob >= 0.80:
                print(f"  【信念】{label} {arrow} 确信度 {prob:.0%} ⚡")
            else:
                print(f"  【信念】{label} {arrow} 确信度 {prob:.0%}")

    # Canon changes (canon events + hard facts)
    # transient_events are narration-only, not displayed as canon
    events = rec.canon_delta.get("events") or []
    added = rec.canon_delta.get("facts_added") or []
    removed = rec.canon_delta.get("facts_removed") or []
    if events or added or removed:
        print()
        for ev in events:
            print(f"  【正典】{_cn_event(ev)}")
        for f in added:
            if not _is_move_fact(f):
                print(f"  【正典】+ {f}")
        for f in removed:
            if not _is_move_fact(f):
                print(f"  【正典】- {f}")

    # Retropath
    if rec.retropath_text and rec.retropath_status == "canonized":
        print()
        target = rec.retropath_text.splitlines()[0].replace("RETROPATH ", "")
        print(f"  【溯因封圣】{_cn_belief(target)}")
        for line in rec.retropath_text.splitlines():
            if line.startswith("CAUSE"):
                print(f"    → 原因: {line.replace('CAUSE ', '')}")
            if line.startswith("EXPLAINS"):
                print(f"    → 解释: {_cn_event(line.replace('EXPLAINS ', ''))}")

    # New facts from retrodiction
    if rec.canon_added_via_retro:
        for f in rec.canon_added_via_retro:
            print(f"    + {f}")


def _is_move_fact(f: Any) -> bool:
    """Suppress at(player,...) facts in compact view (already shown in status panel)."""
    if isinstance(f, Fact):
        return f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player"
    s = str(f)
    return s.startswith("at(player,")


def _humanize_rejection(reason: str) -> str:
    mapping = {
        "not_same_location": "你们不在同一个地方",
        "missing_required_location": "地点不符",
        "speaker_does_not_know_required_fact": "对方不知道这件事",
        "location_inaccessible": "那个地方进不去",
        "location_sealed": "那个地方被封了",
        "unparseable_input": "没听懂你想做什么",
    }
    for key, msg in mapping.items():
        if key in reason:
            return msg
    return reason.replace("_", " ")


# ---------- debug turn output ----------

def _print_turn_debug(rec: TurnRecord) -> None:
    print(f"\n--- turn {rec.turn} ---")

    # v0.2 meta-act info
    if rec.metaact_summary:
        print(f"META-ACT: {rec.metaact_summary}")
    if rec.hypothesis_kind:
        conf = rec.hypothesis_confidence
        print(f"HYPOTHESIS: {rec.hypothesis_kind} (置信度 {conf:.0%})")
    if rec.claim_summary:
        print("CLAIMS:")
        for name, status, reason in rec.claim_summary:
            icon = _claim_status_icon(status)
            print(f"  {icon} {name} [{status}] {reason}")

    if rec.touched:
        print(f"TOUCHED {' '.join(sorted(rec.touched))}")
    if rec.touched_frontiers:
        print(f"FRONTIERS: {' '.join(rec.touched_frontiers)}")
    if rec.budget_class:
        print(f"BUDGET: {rec.budget_class}")
    if rec.affordance_candidates:
        print("AFFORDANCES:")
        for ac in rec.affordance_candidates[:5]:
            print(f"  {ac}")
    if rec.slice_text:
        print("LOCAL SLICE:")
        print(_indent(rec.slice_text))
    print("PATCH:")
    print(_indent(rec.patch_text))
    if rec.validation.ok:
        print("VALIDATION accepted")
    else:
        print(f"VALIDATION rejected: {rec.validation.reason}")
    if rec.belief_modulation:
        print("BELIEF DELTAS:")
        for desc, raw, applied, prob in rec.belief_modulation:
            print(f"  {desc} raw={raw:+.2f} applied={applied:+.3f} -> p={prob:.2f}")
    if rec.canon_delta:
        added = rec.canon_delta.get("facts_added") or []
        removed = rec.canon_delta.get("facts_removed") or []
        if added or removed:
            print("CANON DELTA:")
            for f in added:
                print(f"  + {f}")
            for f in removed:
                print(f"  - {f}")
    if rec.retropath_text:
        print(f"RETROPATH ({rec.retropath_status}):")
        print(_indent(rec.retropath_text))
        if rec.canon_added_via_retro:
            print("CANONIZED VIA RETRO:")
            for f in rec.canon_added_via_retro:
                print(f"  + {f}")
    if rec.narration:
        print("NARRATION:")
        print(_indent(rec.narration))


# ---------- utilities ----------

def _render_full_matrix(world: WorldState) -> str:
    lines: list[str] = []
    for f in sorted(world.facts, key=str):
        lines.append(dsl.render_fact(f))
    for k in sorted(world.knowledge, key=lambda x: (x.agent, str(x.fact))):
        lines.append(dsl.render_knowledge(k))
    for r in world.relations.values():
        lines.append(dsl.render_relation(r))
    for m in world.motifs.values():
        lines.append(dsl.render_motif(m))
    for b in world.beliefs.values():
        lines.append(dsl.render_belief(b))
    if world.frontier:
        lines.append(dsl.render_frontier(world.frontier))
    return "\n".join(lines)


def _render_frontiers(world: WorldState) -> str:
    lines: list[str] = ["  FRONTIER REGISTRY"]
    if not hasattr(world, "frontiers") or not world.frontiers:
        lines.append("  (no registered frontiers)")
        return "\n".join(lines)
    for fid, f in sorted(world.frontiers.items()):
        status_icon = {"compressed": "○", "expanding": "◐", "expanded": "●", "frozen": "✗"}.get(f.status.value, "?")
        lines.append(
            f"  {status_icon} {fid}: {f.kind.value} anchor={f.anchor_entity} loc={f.location} "
            f"salience={f.salience:.2f} status={f.status.value}"
        )
    return "\n".join(lines)


def _render_affordance_debug(world: WorldState) -> str:
    lines: list[str] = ["  AFFORDANCE DEBUG"]
    if not hasattr(world, "frontiers") or not world.frontiers:
        lines.append("  (no frontiers)")
        return "\n".join(lines)
    active = [f for f in world.frontiers.values() if f.status.value != "frozen"]
    lines.append(f"  active frontiers: {len(active)}")
    for f in sorted(active, key=lambda x: -x.salience)[:5]:
        lines.append(f"    - {f.id} ({f.kind.value}) score={f.salience:.2f}")
    return "\n".join(lines)


def _tail_archive(path: str, n: int = 10) -> None:
    if not path or not os.path.exists(path):
        print("  (档案为空)")
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[-n:]:
        obj = line.strip()
        if obj:
            print(f"  {obj}")


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _claim_status_icon(status: str) -> str:
    mapping = {
        "accepted": "[✓]",
        "inferred": "[~]",
        "probable": "[?]",
        "unknown": "[?]",
        "rejected": "[✗]",
    }
    return mapping.get(status, "[?]")


def mode_desc(mode: str) -> str:
    return {"mock": "纯模板", "llm": "LLM润色"}.get(mode, mode)


if __name__ == "__main__":
    sys.exit(main())
