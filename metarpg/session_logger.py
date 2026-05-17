"""Per-session human-readable interaction log.

Writes a Markdown file to `runtime/session_YYYYMMDD_HHMMSS.md` that records
each turn's state, narration, belief changes, and canon deltas in a readable
format. Complements the machine-oriented `cold_archive_*.jsonl`.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .engine import TurnRecord
from .models import WorldState


# ---------- Chinese name maps (presentation layer) ----------

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


class SessionLogger:
    """Writes a Markdown session log."""

    def __init__(self, path: str, scenario: str = "greyfen", mode: str = "LLM润色") -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# MetaRPG v0.1 — 游戏记录\n\n")
            f.write(f"- **场景**: {scenario}\n")
            f.write(f"- **模式**: {mode}\n")
            f.write(f"- **开始时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n---\n\n")

    def write_turn(self, rec: TurnRecord, world: WorldState) -> None:
        lines: list[str] = []
        lines.append(f"## 第 {rec.turn} 回合\n")
        lines.append(f"**输入**: {rec.action_text}\n")

        # State snapshot
        loc = _current_location(world)
        nearby = _nearby_npcs(world)
        avail = _available_locations(world)
        beliefs = _key_beliefs(world)

        lines.append("\n**状态**")
        lines.append(f"- 地点: {_cn_loc(loc)}")
        if nearby:
            lines.append(f"- 附近的人: {' ｜ '.join(_cn_npc(n) for n in nearby)}")
        else:
            lines.append("- 附近: 空无一人")
        if avail:
            lines.append(f"- 可去: {' ｜ '.join(_cn_loc(a) for a in avail)}")
        if beliefs:
            parts = [f"{_cn_belief(b[0])}({b[1]:.0%})" for b in beliefs]
            lines.append(f"- 关键线索: {' ｜ '.join(parts)}")
        lines.append("")

        # Validation
        if not rec.validation.ok:
            lines.append(f"**动作被拒绝**: {rec.validation.reason}\n")

        # Narration
        if rec.narration:
            lines.append("**叙事**")
            lines.append(f"{rec.narration}\n")

        # Belief changes
        if rec.belief_modulation:
            lines.append("**信念变化**")
            for desc, raw, applied, prob in rec.belief_modulation:
                arrow = "↑" if applied >= 0 else "↓"
                lines.append(f"- {_cn_belief(desc)} {arrow} 确信度 {prob:.0%}")
            lines.append("")

        # Canon deltas
        added = rec.canon_delta.get("facts_added") or []
        removed = rec.canon_delta.get("facts_removed") or []
        events = rec.canon_delta.get("events") or []
        if added or removed or events:
            lines.append("**正典变化**")
            for ev in events:
                lines.append(f"- {_cn_event(ev)}")
            for f in added:
                lines.append(f"- + {f}")
            for f in removed:
                lines.append(f"- - {f}")
            lines.append("")

        # Retropath
        if rec.retropath_text and rec.retropath_status == "canonized":
            lines.append("**溯因封圣**")
            lines.append(f"- 解释: {_cn_belief(rec.retropath_text.splitlines()[0].replace('RETROPATH ', ''))}")
            for line in rec.retropath_text.splitlines():
                if line.startswith("CAUSE"):
                    lines.append(f"- 原因: {line.replace('CAUSE ', '')}")
                if line.startswith("EXPLAINS"):
                    lines.append(f"- 解释: {_cn_event(line.replace('EXPLAINS ', ''))}")
            lines.append("")

        lines.append("---\n")

        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def close(self) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n**记录结束**\n")


# ---------- helpers for state snapshot ----------

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
    """Top beliefs by probability (≥ 30%)."""
    items = [(b.description, b.prob) for b in world.beliefs.values() if b.prob >= 0.30]
    items.sort(key=lambda x: -x[1])
    return items
