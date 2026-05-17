"""Hypothesis proposer — two-path: command match + heuristic interpretation.

Path A (high confidence): reuse v0.1 parse_input for well-formed commands.
Path B (heuristic): keyword cue matching for free-form player behavior.

The proposer only *proposes* hypotheses. It does not validate claims.
Validation happens in claims.py.
"""
from __future__ import annotations

from . import metaact as metaact_mod
from .claims import validate_claim
from .models import (
    ActHypothesis,
    Claim,
    ClaimStatus,
    MetaAct,
    ProposedEffect,
    SubAct,
    WorldState,
)
from .parsing import compile_action, parse_input
from .scenario_hooks import ScenarioHooks


# ---------- cue dictionaries ----------

_ASK_CUES = {"问", "问问", "打听", "询问", "消息", "最近", "发生什么", "大事", "怎么样", "如何", "什么", "吗", "呢"}
_ORDER_DRINK_CUES = {"酒", "啤酒", "麦芽", "来一杯", "买一杯", "喝点", "ale", "beer", "drink", "要一杯"}
_COMPLAIN_CUES = {"怎么回事", "甚至没有", "没有", "抱怨", "不满", "恼火", "生气", "complain"}
_OBSERVE_CUES = {"看看", "环顾", "观察", "打量", "反应", "看着", "盯", "注视", "看向", "look", "watch"}
_MOVE_CUES = {"去", "走到", "前往", "go", "walk", "move"}
_HELP_CUES = {"帮", "帮助", "assist", "help", "救"}
_CONFRONT_CUES = {"质问", "指责", "挑战", "confront", "accuse"}
_LISTEN_CUES = {"听", "偷听", "listen", " overhear"}

# v0.3 open-act cues
_BREAK_CUES = {"摔碎", "打碎", "砸碎", "smash", "break", "砸"}
_SPILL_CUES = {"洒", "泼", "pour", "spill", "倒"}
_PICK_CUES = {"捡", "找", "拿起", "pick", "find", "拿"}
_THREATEN_CUES = {"吓唬", "威胁", "逼", "threaten", "吓"}
_PROBE_CUES = {"试探", "看反应", "会不会紧张", "probe", "紧张", "反应"}
_PRETEND_CUES = {"假装", "骗", "pretend", "lie", "装作"}
_USE_AS_TOOL_CUES = {"用", "拿", "卡住", "撬开", "cut", "wedge", "block", "塞", "挡住"}

_TOPIC_CUES: dict[tuple[str, str | None], set[str]] = {
    ("local_news", "tavern"): {"大事", "最近", "消息", "发生什么", "news", "local"},
    ("mine", None): {"矿", "矿场", "老矿", "矿口", "mine"},
    ("iven", None): {"艾文", "伊文", "失踪", "矿工", "iven"},
    ("ale", "tavern"): {"酒", "啤酒", "麦芽", "ale", "beer", "drink"},
    ("service", "tavern"): {"服务", "酒", "没有", "抱怨"},
}


# ---------- main entry ----------


def propose(meta: MetaAct, world: WorldState, hooks: ScenarioHooks | None = None) -> list[ActHypothesis]:
    """Generate hypotheses from a MetaAct. Always returns at least one."""
    hypotheses: list[ActHypothesis] = []

    # Path A: high-confidence command match
    cmd_hyp = _try_command_path(meta, world, hooks)
    if cmd_hyp:
        hypotheses.append(cmd_hyp)

    # Path B: heuristic interpretation (only if different act_kind from Path A)
    heur_hyp = _try_heuristic_path(meta, world, hooks)
    if heur_hyp:
        if cmd_hyp is None or heur_hyp.act_kind != cmd_hyp.act_kind:
            hypotheses.append(heur_hyp)

    # Fallback: never empty
    if not hypotheses:
        hypotheses.append(_make_ambiguous_fallback(meta, world))

    return hypotheses


def select_best(hypotheses: list[ActHypothesis]) -> ActHypothesis | None:
    """Pick the highest-confidence hypothesis."""
    if not hypotheses:
        return None
    return max(hypotheses, key=lambda h: h.confidence)


_CORE_CLAIMS = {"same_location", "can_speak_to", "role_supports", "place_supports"}


# ---------- Path A: command match ----------


def _try_command_path(meta: MetaAct, world: WorldState, hooks: ScenarioHooks | None) -> ActHypothesis | None:
    """Try v0.1 parse_input. If it succeeds, wrap into a high-confidence hypothesis."""
    action = parse_input(meta.raw_text)
    if action is None:
        return None

    # Compile the action to get effects
    patch = compile_action(world, action, hooks)

    # Build support claims from patch requirements
    support_claims: list[Claim] = []
    for req in patch.requirements:
        # Parse requirement into claim
        from .dsl import parse_predicate
        try:
            name, args = parse_predicate(req)
            claim = validate_claim(world, name, args)
            support_claims.append(claim)
        except ValueError:
            pass

    # Convert effects to ProposedEffects
    proposed_effects: list[ProposedEffect] = []
    for eff in patch.effects:
        impact = _effect_impact(eff.kind)
        proposed_effects.append(ProposedEffect(kind=eff.kind, payload=eff.payload, impact=impact))

    # Map old verb to act_kind
    act_kind = _verb_to_act_kind(action.verb)

    target = action.args[0] if action.args else ""
    topic = action.args[1] if len(action.args) > 1 else ""

    # If topic is empty, try heuristic topic inference
    if not topic and act_kind == "ask_about_topic":
        inferred = _infer_topic(meta, world)
        if inferred:
            topic = inferred
            # Rebuild effects with the inferred topic
            proposed_effects = []
            for eff in patch.effects:
                impact = _effect_impact(eff.kind)
                # Update event names that contain "something" or empty topic
                payload = eff.payload
                if eff.kind == "event" and "something" in str(payload[0]):
                    payload = (str(payload[0]).replace("something", topic),)
                if eff.kind == "observe" and "topic" in str(payload[0]):
                    payload = (str(payload[0]).replace("topic", topic),)
                proposed_effects.append(ProposedEffect(kind=eff.kind, payload=payload, impact=impact))

    return ActHypothesis(
        act_kind=act_kind,
        confidence=0.95,
        support_claims=support_claims,
        intended_effects=proposed_effects,
        raw_text=meta.raw_text,
        target=target,
        topic=topic,
    )


def _verb_to_act_kind(verb: str) -> str:
    mapping = {
        "ask": "ask_about_topic",
        "go": "move_to_place",
        "observe": "observe_scene_or_entity",
        "confront": "confront_about_topic",
        "help": "help_entity",
        "listen": "listen_to_entities",
        "sneak": "move_to_place",
    }
    return mapping.get(verb, "ambiguous_social_act")


def _effect_impact(kind: str) -> int:
    """Map effect kind to impact level for Path A effects."""
    if kind == "event" or kind == "observe":
        return 0  # flavor
    if kind == "rel_delta":
        return 1  # social
    if kind == "belief_delta":
        return 2  # belief
    if kind in ("add_fact", "remove_fact", "add_knowledge"):
        return 3  # hard fact
    if kind == "motif_delta":
        return 1  # social texture
    return 0


# ---------- Path B: heuristic interpretation ----------


def _try_heuristic_path(meta: MetaAct, world: WorldState, hooks: ScenarioHooks | None) -> ActHypothesis | None:
    """Keyword cue matching for free-form input.

    Checks both surface_cues and the raw text for cue phrases.
    """
    cues = set(meta.surface_cues)
    text = meta.raw_text
    loc = meta.player_location
    nearby = meta.local_entities

    # Merge surface cues with direct text phrase detection
    # (surface_cues may miss multi-word phrases like "怎么回事")
    raw_cues = set(cues)
    for dic in (_ASK_CUES, _ORDER_DRINK_CUES, _COMPLAIN_CUES, _OBSERVE_CUES,
                _MOVE_CUES, _HELP_CUES, _CONFRONT_CUES, _LISTEN_CUES,
                _BREAK_CUES, _SPILL_CUES, _PICK_CUES, _THREATEN_CUES,
                _PROBE_CUES, _PRETEND_CUES, _USE_AS_TOOL_CUES):
        for cue in dic:
            if cue in text:
                raw_cues.add(cue)
    # Also detect topic cues from raw text
    for (_topic, _loc), topic_cues in _TOPIC_CUES.items():
        for cue in topic_cues:
            if cue in text:
                raw_cues.add(cue)

    # === v0.3: open acts (including composites) take priority ===
    open_hyp = _try_open_act_path(meta, world, text, raw_cues)
    if open_hyp:
        return open_hyp

    # Check each act kind in priority order
    if raw_cues & _ASK_CUES:
        return _build_ask_hypothesis(meta, world, raw_cues)

    # Check complain before order_drink since "没有酒" is complain not order
    if raw_cues & _COMPLAIN_CUES:
        return _build_complain_hypothesis(meta, world, raw_cues)

    if raw_cues & _ORDER_DRINK_CUES:
        return _build_order_drink_hypothesis(meta, world, raw_cues)

    if raw_cues & _CONFRONT_CUES:
        return _build_confront_hypothesis(meta, world, raw_cues)

    if raw_cues & _HELP_CUES:
        return _build_help_hypothesis(meta, world, raw_cues)

    if raw_cues & _LISTEN_CUES:
        return _build_listen_hypothesis(meta, world, raw_cues)

    if raw_cues & _MOVE_CUES:
        return _build_move_hypothesis(meta, world, raw_cues)

    if raw_cues & _OBSERVE_CUES:
        return _build_observe_hypothesis(meta, world, raw_cues)

    # No strong cues — ambiguous fallback will be used
    return None


def _build_ask_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)
    topic = _infer_topic(meta, world)
    loc = meta.player_location

    support_claims = [
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("can_speak_to", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
    ]
    if topic and loc:
        support_claims.append(
            Claim("topic_plausible_for_place", (topic, loc), ClaimStatus.UNKNOWN, "待验证")
        )

    effects = [
        ProposedEffect("event", (f"player_asked_{target}_about_{topic or 'something'}",), 0),
        ProposedEffect("observe", (f"{target}_responded_to_{topic or 'topic'}",), 0),
        ProposedEffect("rel_delta", (target, "player", "trust", 0.02), 1),
    ]

    return ActHypothesis(
        act_kind="ask_about_topic",
        confidence=0.75,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
        topic=topic or "",
    )


def _build_order_drink_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=True)
    loc = meta.player_location

    support_claims = [
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("can_speak_to", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("role_supports", (target, "bartender_service"), ClaimStatus.UNKNOWN, "待验证"),
        Claim("place_supports", (loc, "drink_service"), ClaimStatus.UNKNOWN, "待验证"),
        Claim("item_plausible", ("ale", loc), ClaimStatus.UNKNOWN, "待验证"),
    ]

    effects = [
        ProposedEffect("event", (f"player_ordered_ale_from_{target}",), 0),
        ProposedEffect("event", (f"social_signal_player_{target}_ordinary_customer_request",), 0),
        ProposedEffect("rel_delta", (target, "player", "trust", 0.01), 1),
    ]

    return ActHypothesis(
        act_kind="order_drink",
        confidence=0.72,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
        topic="ale",
    )


def _build_complain_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=True)
    loc = meta.player_location

    support_claims = [
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("can_speak_to", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("place_supports", (loc, "drink_service"), ClaimStatus.UNKNOWN, "待验证"),
        Claim("social_tone", (meta.raw_text, "irritated"), ClaimStatus.UNKNOWN, "待验证"),
    ]

    effects = [
        ProposedEffect("event", (f"player_complained_to_{target}_about_no_service",), 0),
        ProposedEffect("event", (f"social_signal_player_{target}_irritated_customer",), 0),
        ProposedEffect("rel_delta", (target, "player", "trust", -0.03), 1),
        ProposedEffect("rel_delta", (target, "player", "fear", 0.01), 1),
    ]

    return ActHypothesis(
        act_kind="complain_about_service",
        confidence=0.68,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
        topic="service",
    )


def _build_confront_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)
    topic = _infer_topic(meta, world)

    support_claims = [
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("can_speak_to", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
    ]

    effects = [
        ProposedEffect("event", (f"player_confronted_{target}_about_{topic or 'something'}",), 0),
        ProposedEffect("observe", (f"{target}_defensive_about_{topic or 'topic'}",), 0),
        ProposedEffect("rel_delta", (target, "player", "trust", -0.08), 1),
        ProposedEffect("rel_delta", (target, "player", "fear", 0.12), 1),
    ]

    return ActHypothesis(
        act_kind="confront_about_topic",
        confidence=0.70,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
        topic=topic or "",
    )


def _build_help_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)

    support_claims = [
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
    ]

    effects = [
        ProposedEffect("event", (f"player_helped_{target}",), 0),
        ProposedEffect("rel_delta", (target, "player", "trust", 0.15), 1),
        ProposedEffect("rel_delta", (target, "player", "fear", -0.05), 1),
    ]

    return ActHypothesis(
        act_kind="help_entity",
        confidence=0.70,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
    )


def _build_listen_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    nearby = meta.local_entities

    support_claims = []
    for npc in nearby:
        support_claims.append(Claim("same_location", ("player", npc), ClaimStatus.UNKNOWN, "待验证"))

    effects = [
        ProposedEffect("event", (f"player_listened_to_{'_and_'.join(nearby) if nearby else 'silence'}",), 0),
    ]

    return ActHypothesis(
        act_kind="listen_to_entities",
        confidence=0.65,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=",".join(nearby) if nearby else "",
    )


def _build_move_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    place = _infer_place(meta, world)
    current_loc = meta.player_location

    support_claims = [
        Claim("destination_exists", (place,), ClaimStatus.UNKNOWN, "待验证"),
        Claim("accessible", (place,), ClaimStatus.UNKNOWN, "待验证"),
    ]
    if current_loc and place:
        support_claims.append(
            Claim("connected_or_traversable", (current_loc, place), ClaimStatus.UNKNOWN, "待验证")
        )

    effects = [
        ProposedEffect("event", (f"player_arrived_at_{place}",), 0),
    ]
    if current_loc and place:
        from .models import Fact
        effects.append(ProposedEffect("remove_fact", (Fact("at", ("player", current_loc)),), 3))
        effects.append(ProposedEffect("add_fact", (Fact("at", ("player", place)),), 3))

    return ActHypothesis(
        act_kind="move_to_place",
        confidence=0.80,
        support_claims=support_claims,
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=place,
    )


def _build_observe_hypothesis(meta: MetaAct, world: WorldState, cues: set[str]) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)
    if not target or target == "scene":
        target = "scene"

    effects = [
        ProposedEffect("event", (f"player_observed_{target}",), 0),
    ]

    return ActHypothesis(
        act_kind="observe_scene_or_entity",
        confidence=0.70,
        support_claims=[],
        intended_effects=effects,
        raw_text=meta.raw_text,
        target=target,
    )


# ---------- fallback ----------


def _make_ambiguous_fallback(meta: MetaAct, world: WorldState) -> ActHypothesis:
    nearby = meta.local_entities
    if nearby:
        target = nearby[0]
        return ActHypothesis(
            act_kind="ambiguous_social_act",
            confidence=0.50,
            support_claims=[
                Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            ],
            intended_effects=[
                ProposedEffect("event", (f"player_spoke_unclearly_to_{target}",), 0),
                ProposedEffect("observe", (f"{target}_acknowledged_or_ignored_player",), 0),
            ],
            raw_text=meta.raw_text,
            target=target,
        )
    return ActHypothesis(
        act_kind="ambiguous_gesture",
        confidence=0.30,
        support_claims=[],
        intended_effects=[
            ProposedEffect("event", ("player_made_unclear_gesture",), 0),
        ],
        raw_text=meta.raw_text,
        target="scene",
    )


# ---------- v0.3 open-act helpers ----------

_OBJ_ALIASES: dict[str, str] = {
    "杯子": "ale_mug",
    "酒杯": "ale_mug",
    "酒瓶": "bottle",
    "啤酒": "ale",
    "酒": "ale",
    "石头": "loose_stone",
    "石块": "loose_stone",
    "碎片": "glass_shard",
    "玻璃片": "glass_shard",
    "地图": "map",
    "椅子": "chair",
    "桌子": "table",
    "蜡烛": "candle",
    "布": "rag",
}


def _infer_object_from_text(text: str, world: WorldState) -> str:
    """Infer the object being manipulated from player text."""
    known = set(world.object_tags.keys())
    for obj in known:
        if obj in text:
            return obj
    for cn, en in _OBJ_ALIASES.items():
        if cn in text:
            return en
    return ""


def _infer_means_from_text(text: str) -> str:
    """Infer the threatening means from player text."""
    if "碎片" in text or "玻璃片" in text or "shard" in text.lower():
        return "glass_shard"
    if "刀" in text or "knife" in text.lower():
        return "knife"
    if "石头" in text or "石块" in text or "stone" in text.lower():
        return "loose_stone"
    return "bare_hands"


def _try_open_act_path(meta: MetaAct, world: WorldState, text: str, raw_cues: set[str]) -> ActHypothesis | None:
    """v0.3 open-act and composite-act hypothesis generation."""
    has_break = any(c in text for c in _BREAK_CUES)
    has_spill = any(c in text for c in _SPILL_CUES)
    has_threaten = any(c in text for c in _THREATEN_CUES)
    has_probe = any(c in text for c in _PROBE_CUES)
    has_pretend = any(c in text for c in _PRETEND_CUES)
    has_pick = any(c in text for c in _PICK_CUES)
    has_use_tool = any(c in text for c in _USE_AS_TOOL_CUES)

    # Composite acts (detected before single acts)
    if has_break and has_threaten:
        return _build_break_threaten_hypothesis(meta, world, text)
    if has_spill and has_probe:
        return _build_spill_probe_hypothesis(meta, world, text)
    if has_pretend and has_probe:
        return _build_pretend_probe_hypothesis(meta, world, text)
    if has_pick and has_use_tool:
        return _build_pick_use_hypothesis(meta, world, text)

    # Single open acts
    if has_break:
        return _build_break_hypothesis(meta, world, text)
    if has_spill:
        return _build_spill_hypothesis(meta, world, text)
    if has_threaten:
        return _build_threaten_hypothesis(meta, world, text)
    if has_pick:
        return _build_pick_hypothesis(meta, world, text)

    # Absent-entity guard test: toast to someone
    if "举杯" in text or "cheers" in text.lower() or "toast" in text.lower():
        return _build_toast_hypothesis(meta, world, text)

    return None


# --- composite act builders ---


def _build_break_threaten_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    loc = meta.player_location
    target = _infer_target(meta, prefer_service_npc=False)
    obj = _infer_object_from_text(text, world) or "ale_mug"
    means = _infer_means_from_text(text)
    if means == "bare_hands" and ("碎片" in text or "玻璃片" in text):
        means = "glass_shard"

    break_result = "glass_shard" if obj in ("ale_mug", "bottle") else "debris"

    break_subact = SubAct(
        kind="break_object",
        actor="player",
        args=(obj,),
        claims=[
            Claim("has_or_near", ("player", obj), ClaimStatus.UNKNOWN, "待验证"),
            Claim("fragile", (obj,), ClaimStatus.UNKNOWN, "待验证"),
            Claim("break_creates", (obj, break_result), ClaimStatus.UNKNOWN, "待验证"),
            Claim("item_plausible", (obj, loc or "unknown"), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("canon_event", (f"player_broke_{obj}",), 1),
            ProposedEffect("add_object", (break_result, loc or "unknown"), 2),
        ],
        impact=2,
    )

    threat_subact = SubAct(
        kind="threaten",
        actor="player",
        args=(target, means),
        claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("can_threaten", ("player", target, means), ClaimStatus.UNKNOWN, "待验证"),
            Claim("no_absent_entity_direct_action", (target,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("rel_delta", (target, "player", "fear", 0.12), 1),
            ProposedEffect("rel_delta", (target, "player", "trust", -0.10), 1),
            ProposedEffect("risk_flag", ("noise_created",), 0),
        ],
        impact=1,
    )

    return ActHypothesis(
        act_kind="composite_physical_social_act",
        confidence=0.70,
        support_claims=[],
        intended_effects=[],
        subacts=[break_subact, threat_subact],
        raw_text=meta.raw_text,
        target=target,
        topic=obj,
    )


def _build_spill_probe_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    loc = meta.player_location
    target = _infer_target(meta, prefer_service_npc=False)
    liquid = _infer_object_from_text(text, world)
    if not liquid or "liquid" not in world.object_tags.get(liquid, set()):
        liquid = "ale"

    # Infer the object being spilled on
    spill_target = ""
    for obj in world.object_tags:
        if obj in text and obj != liquid:
            spill_target = obj
            break
    if not spill_target:
        spill_target = "map" if "地图" in text or "map" in text.lower() else "table"

    spill_subact = SubAct(
        kind="spill",
        actor="player",
        args=(liquid, spill_target),
        claims=[
            Claim("has_or_near", ("player", liquid), ClaimStatus.UNKNOWN, "待验证"),
            Claim("liquid", (liquid,), ClaimStatus.UNKNOWN, "待验证"),
            Claim("object_exists", (spill_target,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("transient_event", (f"player_spilled_{liquid}_on_{spill_target}",), 0),
        ],
        impact=0,
    )

    probe_topic = "mine" if ("矿" in text or "mine" in text.lower()) else "something"
    probe_subact = SubAct(
        kind="observe_reaction",
        actor="player",
        args=(target, probe_topic),
        claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("reaction_observable", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("topic_sensitive_to", (target, probe_topic), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("belief_delta", ("mara_knows_recent_entry", 0.05), 2),
            ProposedEffect("rel_delta", (target, "player", "trust", -0.03), 1),
        ],
        impact=1,
    )

    return ActHypothesis(
        act_kind="composite_act",
        confidence=0.68,
        support_claims=[],
        intended_effects=[],
        subacts=[spill_subact, probe_subact],
        raw_text=meta.raw_text,
        target=target,
        topic=probe_topic,
    )


def _build_pretend_probe_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)
    pretended_topic = "iven" if ("艾文" in text or "iven" in text.lower()) else "something"

    pretend_subact = SubAct(
        kind="deceive",
        actor="player",
        args=(target, pretended_topic),
        claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("can_deceive", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("transient_event", (f"player_pretended_to_know_{pretended_topic}",), 0),
        ],
        impact=0,
    )

    probe_subact = SubAct(
        kind="probe_reaction",
        actor="player",
        args=(target, pretended_topic),
        claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("can_probe_reaction", ("player", target, pretended_topic), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("belief_delta", (f"{target}_knows_about_{pretended_topic}", 0.05), 2),
            ProposedEffect("rel_delta", (target, "player", "trust", -0.02), 1),
        ],
        impact=1,
    )

    return ActHypothesis(
        act_kind="composite_act",
        confidence=0.65,
        support_claims=[],
        intended_effects=[],
        subacts=[pretend_subact, probe_subact],
        raw_text=meta.raw_text,
        target=target,
        topic=pretended_topic,
    )


def _build_pick_use_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    from .models import Fact
    loc = meta.player_location
    obj = _infer_object_from_text(text, world) or "loose_stone"

    tool_function = "wedge"
    if "卡住" in text or "塞" in text or "block" in text.lower() or "挡住" in text:
        tool_function = "block"
    elif "撬" in text:
        tool_function = "wedge"

    pick_subact = SubAct(
        kind="pick_object",
        actor="player",
        args=(obj,),
        claims=[
            Claim("can_materialize", (obj, loc or "unknown", "1"), ClaimStatus.UNKNOWN, "待验证"),
            Claim("movable", (obj,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("add_object", (obj, loc or "unknown"), 2),
            ProposedEffect("add_fact", (Fact("has", ("player", obj)),), 3),
        ],
        impact=2,
    )

    use_subact = SubAct(
        kind="use_as_tool",
        actor="player",
        args=(obj, tool_function),
        claims=[
            Claim("has", ("player", obj), ClaimStatus.UNKNOWN, "待验证"),
            Claim("use_as_tool", (obj, tool_function), ClaimStatus.UNKNOWN, "待验证"),
        ],
        effects=[
            ProposedEffect("transient_event", (f"player_used_{obj}_to_{tool_function}",), 0),
        ],
        impact=0,
    )

    return ActHypothesis(
        act_kind="composite_act",
        confidence=0.65,
        support_claims=[],
        intended_effects=[],
        subacts=[pick_subact, use_subact],
        raw_text=meta.raw_text,
        target=obj,
        topic=tool_function,
    )


# --- single open-act builders ---


def _build_break_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    loc = meta.player_location
    obj = _infer_object_from_text(text, world) or "ale_mug"
    break_result = "glass_shard" if obj in ("ale_mug", "bottle") else "debris"

    return ActHypothesis(
        act_kind="physical_manipulation",
        confidence=0.65,
        support_claims=[
            Claim("has_or_near", ("player", obj), ClaimStatus.UNKNOWN, "待验证"),
            Claim("fragile", (obj,), ClaimStatus.UNKNOWN, "待验证"),
            Claim("break_creates", (obj, break_result), ClaimStatus.UNKNOWN, "待验证"),
            Claim("item_plausible", (obj, loc or "unknown"), ClaimStatus.UNKNOWN, "待验证"),
        ],
        intended_effects=[
            ProposedEffect("canon_event", (f"player_broke_{obj}",), 1),
            ProposedEffect("add_object", (break_result, loc or "unknown"), 2),
        ],
        raw_text=meta.raw_text,
        target=obj,
    )


def _build_threaten_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)
    means = _infer_means_from_text(text)

    return ActHypothesis(
        act_kind="threat_or_pressure",
        confidence=0.65,
        support_claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("can_threaten", ("player", target, means), ClaimStatus.UNKNOWN, "待验证"),
        ],
        intended_effects=[
            ProposedEffect("rel_delta", (target, "player", "fear", 0.12), 1),
            ProposedEffect("rel_delta", (target, "player", "trust", -0.10), 1),
        ],
        raw_text=meta.raw_text,
        target=target,
    )


def _build_spill_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    liquid = _infer_object_from_text(text, world)
    if not liquid or "liquid" not in world.object_tags.get(liquid, set()):
        liquid = "ale"

    return ActHypothesis(
        act_kind="physical_manipulation",
        confidence=0.60,
        support_claims=[
            Claim("has_or_near", ("player", liquid), ClaimStatus.UNKNOWN, "待验证"),
            Claim("liquid", (liquid,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        intended_effects=[
            ProposedEffect("transient_event", (f"player_spilled_{liquid}",), 0),
        ],
        raw_text=meta.raw_text,
        target=liquid,
    )


def _build_pick_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    loc = meta.player_location
    obj = _infer_object_from_text(text, world) or "loose_stone"

    return ActHypothesis(
        act_kind="object_materialization",
        confidence=0.60,
        support_claims=[
            Claim("can_materialize", (obj, loc or "unknown", "1"), ClaimStatus.UNKNOWN, "待验证"),
            Claim("movable", (obj,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        intended_effects=[
            ProposedEffect("add_object", (obj, loc or "unknown"), 2),
        ],
        raw_text=meta.raw_text,
        target=obj,
    )


def _build_toast_hypothesis(meta: MetaAct, world: WorldState, text: str) -> ActHypothesis:
    target = _infer_target(meta, prefer_service_npc=False)

    return ActHypothesis(
        act_kind="communicative_act",
        confidence=0.60,
        support_claims=[
            Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
            Claim("no_absent_entity_direct_action", (target,), ClaimStatus.UNKNOWN, "待验证"),
        ],
        intended_effects=[
            ProposedEffect("transient_event", (f"player_toasted_to_{target}",), 0),
        ],
        raw_text=meta.raw_text,
        target=target,
    )


# ---------- inference helpers ----------


def _infer_target(meta: MetaAct, prefer_service_npc: bool = False) -> str:
    """Infer the target entity from MetaAct cues.

    Priority:
    1. Explicit named entity in surface cues
    2. Service NPC if prefer_service_npc
    3. Nearest NPC
    4. 'scene'
    """
    cues = set(meta.surface_cues)
    nearby = meta.local_entities

    # 1. Explicit name
    for npc in nearby:
        if npc in cues:
            return npc
    # Also check Chinese names
    name_map = {"玛拉": "mara", "拉斯克": "rusk", "艾文": "iven", "伊文": "iven"}
    for cn, en in name_map.items():
        if cn in cues and en in nearby:
            return en

    # 2. Service NPC preference
    if prefer_service_npc and nearby:
        # Simplified heuristics based on location
        if meta.player_location == "tavern" and "mara" in nearby:
            return "mara"
        if meta.player_location == "guard_post" and "rusk" in nearby:
            return "rusk"

    # 3. Nearest NPC
    if nearby:
        return nearby[0]

    return "scene"


def _infer_topic(meta: MetaAct, world: WorldState) -> str:
    """Infer topic from surface cues and raw text."""
    cues = set(meta.surface_cues)
    text = meta.raw_text
    loc = meta.player_location

    for (topic, topic_loc), topic_cues in _TOPIC_CUES.items():
        if topic_loc and topic_loc != loc:
            continue
        # Check both surface cues and raw text
        if cues & topic_cues:
            return topic
        for cue in topic_cues:
            if cue in text:
                return topic

    return ""


def _infer_place(meta: MetaAct, world: WorldState) -> str:
    """Infer destination place from surface cues."""
    cues = set(meta.surface_cues)
    for loc in world.locations:
        if loc in cues:
            return loc
    # Chinese location names
    loc_map = {
        "酒馆": "tavern",
        "守卫站": "guard_post",
        "老矿": "old_mine",
        "矿场": "old_mine",
        "矿口": "old_mine_gate",
        "地窖": "mara_cellar",
    }
    for cn, en in loc_map.items():
        if cn in cues:
            return en

    return ""
