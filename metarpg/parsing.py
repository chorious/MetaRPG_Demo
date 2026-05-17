"""Input parsing and action compilation — extracted from engine.py to avoid circular imports.

v0.1 keyword parser + default compilers. Used by engine.py and proposer.py.
"""
from __future__ import annotations

import re
from typing import Any

from .models import Action, Effect, Fact, Patch, WorldState
from .scenario_hooks import ScenarioHooks


_STOPWORDS = {"the", "a", "an", "to", "at", "about", "and", "with"}
_VERB_ALIASES = {
    "talk": "ask",
    "speak": "ask",
    "say": "ask",
    "move": "go",
    "walk": "go",
    "look": "observe",
    "watch": "observe",
    "challenge": "confront",
    "accuse": "confront",
    "offer": "help",
}

_CN_TO_EN = {
    "问问": "ask",
    "问": "ask",
    "去": "go",
    "前往": "go",
    "走到": "go",
    "走": "go",
    "看": "observe",
    "观察": "observe",
    "质问": "confront",
    "帮": "help",
    "帮助": "help",
    "听": "listen",
    "潜入": "sneak",
    "关于": "about",
    "和": "and",
    "到": "to",
    "在": "at",
    "跟": "with",
    "的": "",
    "那个": "",
    "玛拉": "mara",
    "拉斯克": "rusk",
    "艾文": "iven",
    "伊文": "iven",
    "酒馆": "tavern",
    "守卫站": "guard_post",
    "老矿": "old_mine",
    "矿场": "mine",
    "矿口": "old_mine_gate",
    "地窖": "mara_cellar",
}

_CN_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_CN_TO_EN, key=len, reverse=True))
)


def _translate_input(text: str) -> str:
    def _repl(m: re.Match) -> str:
        replacement = _CN_TO_EN[m.group(0)]
        return (replacement + " ") if replacement else " "
    cleaned = text.strip()
    for ch in "，。！？；：":
        cleaned = cleaned.replace(ch, " ")
    cleaned = cleaned.replace("　", " ")
    return _CN_PATTERN.sub(_repl, cleaned).strip()


def parse_input(text: str) -> Action | None:
    """v0.1 keyword parser — preserved for Path A command matching.

    v0.2.1: if parsed target/topic/place is not in the canonical whitelist,
    returns None so the MetaAct proposer can handle it.
    """
    text = _translate_input(text)
    s = text.strip().lower()
    if not s:
        return None
    tokens = [t for t in s.replace(",", " ").split() if t]
    if not tokens:
        return None
    verb = _VERB_ALIASES.get(tokens[0], tokens[0])
    action: Action | None = None

    if verb == "ask":
        rest = tokens[1:]
        target, topic = "", ""
        if "about" in rest:
            i = rest.index("about")
            tgt_tokens = [t for t in rest[:i] if t not in _STOPWORDS]
            top_tokens = [t for t in rest[i + 1 :] if t not in _STOPWORDS]
            target = tgt_tokens[0] if tgt_tokens else ""
            topic = "_".join(top_tokens) if top_tokens else ""
        else:
            tgt_tokens = [t for t in rest if t not in _STOPWORDS]
            target = tgt_tokens[0] if tgt_tokens else ""
        action = Action("ask", (target, topic), text)

    elif verb == "go":
        rest = [t for t in tokens[1:] if t not in _STOPWORDS]
        place = "_".join(rest)
        action = Action("go", (place,), text)

    elif verb == "observe":
        rest = [t for t in tokens[1:] if t not in _STOPWORDS]
        target = rest[0] if rest else "scene"
        action = Action("observe", (target,), text)

    elif verb == "confront":
        rest = tokens[1:]
        target, topic = "", ""
        if "about" in rest:
            i = rest.index("about")
            tgt_tokens = [t for t in rest[:i] if t not in _STOPWORDS]
            top_tokens = [t for t in rest[i + 1 :] if t not in _STOPWORDS]
            target = tgt_tokens[0] if tgt_tokens else ""
            topic = "_".join(top_tokens) if top_tokens else ""
        else:
            tgt_tokens = [t for t in rest if t not in _STOPWORDS]
            target = tgt_tokens[0] if tgt_tokens else ""
        action = Action("confront", (target, topic), text)

    elif verb == "help":
        rest = [t for t in tokens[1:] if t not in _STOPWORDS]
        target = rest[0] if rest else ""
        action = Action("help", (target,), text)

    elif verb == "listen":
        rest = [t for t in tokens[1:] if t not in _STOPWORDS]
        action = Action("listen", tuple(rest), text)

    elif verb == "sneak":
        rest = [t for t in tokens[1:] if t not in _STOPWORDS]
        place = "_".join(rest)
        action = Action("sneak", (place,), text)

    # v0.2.1: whitelist filter — unknown targets/topics/places fall through to MetaAct proposer
    if action and not _in_whitelist(action):
        return None
    return action


# Whitelist of canonical entities/locations/topics for Path A command parser
_WHITELIST_ENTITIES = {"player", "mara", "rusk", "iven", "someone", "scene", "silence"}
_WHITELIST_LOCATIONS = {"tavern", "guard_post", "old_mine_gate", "mara_cellar", "old_mine"}
_WHITELIST_TOPICS = {"mine", "old_mine", "iven", "local_news", "service", "ale", "something", "topic", "silence"}


def _in_whitelist(action: Action) -> bool:
    """Check if action args contain only canonical entities/locations/topics."""
    for arg in action.args:
        if not arg:
            continue
        # Check the full arg first (for multi-word like guard_post)
        if arg in _WHITELIST_ENTITIES:
            continue
        if arg in _WHITELIST_LOCATIONS:
            continue
        if arg in _WHITELIST_TOPICS:
            continue
        # Split by underscore for multi-word args
        parts = arg.split("_")
        for p in parts:
            if not p:
                continue
            if p in _WHITELIST_ENTITIES:
                continue
            if p in _WHITELIST_LOCATIONS:
                continue
            if p in _WHITELIST_TOPICS:
                continue
            return False
    return True


# ---------- default action compilers ----------


def _compile_go(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    place = action.args[0]
    patch = Patch(intent=f"go(player,{place})")
    patch.requirements.append(f"accessible({place})")
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            patch.effects.append(Effect("remove_fact", (f,)))
            break
    patch.effects.append(Effect("add_fact", (Fact("at", ("player", place)),)))
    patch.effects.append(Effect("event", (f"player_arrived_at_{place}",)))
    return patch


def _compile_observe(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    target = action.args[0]
    patch = Patch(intent=f"observe(player,{target})")
    patch.effects.append(Effect("event", (f"player_observed_{target}",)))
    for m in world.motifs.values():
        if target in m.args:
            patch.effects.append(Effect("motif_delta", (m.name, m.args, "salience", 0.05)))
    return patch


def _compile_help(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    target = action.args[0]
    patch = Patch(intent=f"help(player,{target})")
    if target:
        patch.requirements.append(f"same_location(player,{target})")
    patch.effects.append(Effect("event", (f"player_helped_{target}",)))
    if target:
        patch.effects.append(Effect("rel_delta", (target, "player", "trust", 0.15)))
        patch.effects.append(Effect("rel_delta", (target, "player", "fear", -0.05)))
    return patch


def _compile_sneak(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    place = action.args[0]
    patch = Patch(intent=f"sneak(player,{place})")
    patch.requirements.append(f"at(player,{place}_gate)")
    patch.requirements.append(f"accessible({place})")
    patch.effects.append(Effect("add_fact", (Fact("at", ("player", place)),)))
    patch.effects.append(Effect("event", (f"player_sneaked_into_{place}",)))
    return patch


def _compile_ask(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    target, topic = action.args[0], action.args[1]
    topic_key = topic.replace("old_", "") if topic.startswith("old_") else topic
    patch = Patch(intent=f"ask(player,{target},{topic})")
    if target:
        patch.requirements.append(f"same_location(player,{target})")
    patch.effects.append(Effect("event", (f"player_asked_{target or 'someone'}_about_{topic or 'something'}",)))
    if target:
        patch.effects.append(Effect("observe", (f"{target}_evasive_about_{topic_key or 'topic'}",)))
        patch.effects.append(Effect("rel_delta", (target, "player", "trust", 0.04)))
    impacts = (hooks.topic_impacts if hooks else {}).get(("ask", topic), [])
    for desc, base in impacts:
        patch.effects.append(Effect("belief_delta", (desc, base)))
    return patch


def _compile_confront(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    target, topic = action.args[0], action.args[1]
    patch = Patch(intent=f"confront(player,{target},{topic})")
    if target:
        patch.requirements.append(f"same_location(player,{target})")
    patch.effects.append(Effect("event", (f"player_confronted_{target}_about_{topic or 'something'}",)))
    if target:
        patch.effects.append(Effect("observe", (f"{target}_defensive_about_{topic or 'topic'}",)))
        patch.effects.append(Effect("rel_delta", (target, "player", "trust", -0.08)))
        patch.effects.append(Effect("rel_delta", (target, "player", "fear", 0.12)))
    impacts = (hooks.topic_impacts if hooks else {}).get(("confront", topic), [])
    for desc, base in impacts:
        patch.effects.append(Effect("belief_delta", (desc, base)))
    return patch


def _compile_listen(action: Action, world: WorldState, hooks: ScenarioHooks | None) -> Patch:
    targets = [t for t in action.args if t]
    patch = Patch(intent=f"listen(player,{','.join(targets) or 'silence'})")
    if not targets:
        patch.effects.append(Effect("event", ("player_listened_to_silence",)))
        return patch
    for t in targets:
        patch.requirements.append(f"same_location(player,{t})")
    patch.effects.append(Effect("event", (f"player_listened_to_{'_and_'.join(targets)}",)))
    return patch


_DEFAULT_COMPILERS: dict[str, Any] = {
    "go": _compile_go,
    "observe": _compile_observe,
    "help": _compile_help,
    "sneak": _compile_sneak,
    "ask": _compile_ask,
    "confront": _compile_confront,
    "listen": _compile_listen,
}


def compile_action(world: WorldState, action: Action, hooks: ScenarioHooks | None = None) -> Patch:
    """Module-level compile. Uses default compilers + scenario overrides."""
    compilers = dict(_DEFAULT_COMPILERS)
    if hooks and hooks.action_compilers:
        compilers.update(hooks.action_compilers)
    compiler = compilers.get(action.verb)
    if compiler:
        return compiler(action, world, hooks)
    return Patch(
        intent=f"unknown({action.text})",
        requirements=["unrecognized_verb"],
        effects=[],
    )
