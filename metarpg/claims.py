"""Claim validation — v0.2 claim substrate.

Each claim validator receives (world, claim_args) and returns a Claim with one
of five statuses: ACCEPTED, INFERRED, PROBABLE, UNKNOWN, REJECTED.

The proposer writes claims; code validates them. No LLM output is used for
validation.
"""
from __future__ import annotations

from .models import Claim, ClaimStatus, Fact, WorldState


# ---------- social tone cue maps ----------

_TONE_CUES: dict[str, set[str]] = {
    "irritated": {"怎么回事", "甚至没有", "没有", "抱怨", "不满", "恼火", "生气", "愤怒"},
    "friendly": {"帮", "帮助", "谢谢", "感谢", "微笑", "你好"},
    "threatening": {"威胁", "小心", "警告", "别逼我", "你会后悔"},
    "sad": {"难过", "伤心", "叹息", "哭泣", "流泪"},
    "curious": {"问问", "打听", "为什么", "怎么回事", "什么", "怎么"},
    "ordinary": {"来一杯", "买", "要", "请", "麻烦"},
}


# ---------- main entry ----------


def validate_claim(world: WorldState, claim_name: str, args: tuple[str, ...]) -> Claim:
    """Validate a single claim against world state. Returns a Claim with status."""
    validator = _VALIDATORS.get(claim_name)
    if validator:
        status, reason = validator(world, args)
        return Claim(name=claim_name, args=args, status=status, reason=reason)
    # Unknown claim type: default to UNKNOWN
    return Claim(
        name=claim_name, args=args, status=ClaimStatus.UNKNOWN, reason="未知声明类型"
    )


def validate_hypothesis_support_claims(world: WorldState, support_claims: list[Claim]) -> list[Claim]:
    """Re-validate all support claims in a hypothesis. Returns updated claims."""
    out: list[Claim] = []
    for c in support_claims:
        validated = validate_claim(world, c.name, c.args)
        out.append(validated)
    return out


# ---------- validators ----------


def _validate_same_location(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    a, b = args[0], args[1]
    la = _location_of(world, a)
    lb = _location_of(world, b)
    if la and lb and la == lb:
        return ClaimStatus.ACCEPTED, f"{a} 和 {b} 同在 {la}"
    if la and lb:
        return ClaimStatus.REJECTED, f"{a} 在 {la}，{b} 在 {lb}"
    return ClaimStatus.UNKNOWN, f"位置信息不足"


def _validate_can_speak_to(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    a, b = args[0], args[1]
    # Must be same location
    loc_a = _location_of(world, a)
    loc_b = _location_of(world, b)
    if loc_a != loc_b or not loc_a:
        return ClaimStatus.REJECTED, f"{a} 和 {b} 不在同一地点"
    # Target must be an NPC (or player)
    if b != "player" and b not in world.npcs:
        return ClaimStatus.REJECTED, f"{b} 不是可交谈对象"
    return ClaimStatus.ACCEPTED, f"{a} 可以与 {b} 交谈"


def _validate_role_supports(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    entity, service = args[0], args[1]
    roles = world.roles.get(entity, set())
    if service in roles:
        return ClaimStatus.ACCEPTED, f"{entity} 具有角色 {service}"
    # Infer from role name similarity (heuristic)
    for role in roles:
        if service in role or role in service:
            return ClaimStatus.INFERRED, f"{entity} 的角色 {role} 可能支持 {service}"
    return ClaimStatus.UNKNOWN, f"{entity} 的角色信息未知"


def _validate_place_supports(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    place, service = args[0], args[1]
    services = world.place_services.get(place, set())
    if service in services:
        return ClaimStatus.ACCEPTED, f"{place} 提供 {service}"
    for svc in services:
        if service in svc or svc in service:
            return ClaimStatus.INFERRED, f"{place} 的服务 {svc} 可能包含 {service}"
    return ClaimStatus.UNKNOWN, f"{place} 的服务信息未知"


def _validate_item_plausible(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    item, place = args[0], args[1]
    items = world.item_plausibility.get(place, set())
    if item in items:
        return ClaimStatus.ACCEPTED, f"{place} 可能有 {item}"
    for it in items:
        if item in it or it in item:
            return ClaimStatus.PROBABLE, f"{place} 的物品 {it} 与 {item} 相似"
    return ClaimStatus.UNKNOWN, f"{place} 的物品信息未知"


def _validate_social_tone(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    raw_text, tone = args[0], args[1]
    cues = _TONE_CUES.get(tone, set())
    if any(c in raw_text for c in cues):
        return ClaimStatus.INFERRED, f"文本中包含 {tone} 的语气线索"
    return ClaimStatus.UNKNOWN, f"未检测到 {tone} 的语气线索"


def _validate_topic_plausible_for_place(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    topic, place = args[0], args[1]
    topics = world.place_topics.get(place, set())
    if topic in topics:
        return ClaimStatus.ACCEPTED, f"{place} 关联话题 {topic}"
    for t in topics:
        if topic in t or t in topic:
            return ClaimStatus.INFERRED, f"{place} 的话题 {t} 与 {topic} 相关"
    return ClaimStatus.UNKNOWN, f"{place} 的话题信息未知"


def _validate_not_contradicts_locked_fact(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    stmt = args[0]
    # Simple check: if the statement corresponds to a negated fact
    # e.g., "mine is open" contradicts sealed(old_mine)
    # For v0.2, do a keyword-based check against hard canon
    if "open" in stmt.lower() and Fact("sealed", ("old_mine",)) in world.facts:
        return ClaimStatus.REJECTED, "老矿已被封印"
    if "alive" in stmt.lower() and Fact("dead", ("iven",)) in world.facts:
        return ClaimStatus.REJECTED, "艾文已死"
    if "dead" in stmt.lower() and Fact("alive", ("iven",)) in world.facts:
        return ClaimStatus.REJECTED, "艾文活着"
    return ClaimStatus.ACCEPTED, "未与正典冲突"


def _validate_reachable(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    a, b = args[0], args[1]
    loc_a = _location_of(world, a)
    loc_b = _location_of(world, b)
    if loc_a and loc_b and loc_a == loc_b:
        return ClaimStatus.ACCEPTED, f"{a} 和 {b} 在同一地点"
    # Adjacent locations are reachable (simple heuristic)
    return ClaimStatus.PROBABLE, f"{a} 到 {b} 的距离未定义，假设可达"


def _validate_plausible_scene_object(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, place = args[0], args[1]
    return _validate_item_plausible(world, args)


def _validate_accessible(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    place = args[0]
    sealed = Fact("sealed", (place,)) in world.facts
    if not sealed:
        return ClaimStatus.ACCEPTED, f"{place} 未被封印"
    if Fact("holds_key", ("player", place)) in world.facts:
        return ClaimStatus.ACCEPTED, f"持有 {place} 的钥匙"
    if Fact("permission", ("player", place)) in world.facts:
        return ClaimStatus.ACCEPTED, f"有进入 {place} 的许可"
    if Fact("opened", (place,)) in world.facts:
        return ClaimStatus.ACCEPTED, f"{place} 已开启"
    return ClaimStatus.REJECTED, f"{place} 被封印，无法进入"


def _validate_movable(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    # In v0.2, assume small loose objects are movable
    small_objects = {"loose_stone", "stone", "rock", "stick", "pebble"}
    if obj in small_objects or any(s in obj for s in small_objects):
        return ClaimStatus.INFERRED, f"{obj} 看起来可以移动"
    return ClaimStatus.UNKNOWN, f"{obj} 的可移动性未知"


def _validate_destination_exists(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    place = args[0]
    if place in world.locations:
        return ClaimStatus.ACCEPTED, f"{place} 是已知地点"
    return ClaimStatus.REJECTED, f"{place} 不是已知地点"


def _validate_connected_or_traversable(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    current, dest = args[0], args[1]
    if current == dest:
        return ClaimStatus.REJECTED, "已经在目的地"
    # Simple heuristic: all locations are connected in this village
    if current in world.locations and dest in world.locations:
        return ClaimStatus.INFERRED, f"{current} 与 {dest} 之间有路径"
    return ClaimStatus.UNKNOWN, f"{current} 到 {dest} 的连通性未知"


# ---------- v0.3 claim families ----------

# 5.1 Existence / Materialization


def _validate_object_exists(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    if obj in world.object_tags:
        return ClaimStatus.ACCEPTED, f"{obj} 是已知物体"
    for f in world.facts:
        if obj in f.args:
            return ClaimStatus.ACCEPTED, f"{obj} 存在于正典中"
    return ClaimStatus.UNKNOWN, f"{obj} 未知"


def _validate_object_near(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, obj = args[0], args[1]
    actor_loc = _location_of(world, actor)
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == obj and f.args[1] == actor_loc:
            return ClaimStatus.ACCEPTED, f"{obj} 在 {actor_loc}"
    if actor_loc:
        status, reason = _validate_item_plausible(world, (obj, actor_loc))
        if status in (ClaimStatus.ACCEPTED, ClaimStatus.PROBABLE, ClaimStatus.INFERRED):
            return status, reason
    return ClaimStatus.UNKNOWN, f"{obj} 位置未知"


def _validate_has(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, obj = args[0], args[1]
    if Fact("has", (actor, obj)) in world.facts:
        return ClaimStatus.ACCEPTED, f"{actor} 持有 {obj}"
    return ClaimStatus.UNKNOWN, f"{actor} 是否持有 {obj} 未知"


def _validate_has_or_near(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, obj = args[0], args[1]
    has_result = _validate_has(world, args)
    if has_result[0] == ClaimStatus.ACCEPTED:
        return has_result
    near_result = _validate_object_near(world, args)
    if near_result[0] in (ClaimStatus.ACCEPTED, ClaimStatus.PROBABLE, ClaimStatus.INFERRED):
        return near_result
    actor_loc = _location_of(world, actor)
    if actor_loc:
        status, reason = _validate_item_plausible(world, (obj, actor_loc))
        if status in (ClaimStatus.ACCEPTED, ClaimStatus.PROBABLE, ClaimStatus.INFERRED):
            return ClaimStatus.PROBABLE, f"{obj} 可能在 {actor_loc} 附近"
    return ClaimStatus.UNKNOWN, f"{obj} 不可见"


def _validate_can_materialize(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, place = args[0], args[1]
    impact = int(args[2]) if len(args) > 2 else 1
    status, reason = _validate_item_plausible(world, (obj, place))
    if status == ClaimStatus.ACCEPTED:
        return ClaimStatus.ACCEPTED, f"{obj} 可以在 {place} 找到"
    if status == ClaimStatus.PROBABLE:
        if impact <= 1:
            return ClaimStatus.ACCEPTED, f"{obj} 是 {place} 的低影响道具，允许物质化"
        return ClaimStatus.PROBABLE, f"{obj} 在 {place} 可能出现"
    if status == ClaimStatus.INFERRED:
        if impact <= 1:
            return ClaimStatus.ACCEPTED, f"{obj} 在 {place} 推断可物质化"
        return ClaimStatus.INFERRED, f"{obj} 在 {place} 推断可能出现"
    return ClaimStatus.REJECTED, f"{obj} 在 {place} 出现不合理"


# 5.2 Physical Properties


def _validate_fragile(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    tags = world.object_tags.get(obj, set())
    if "fragile" in tags:
        return ClaimStatus.ACCEPTED, f"{obj} 是易碎物"
    if "rigid" in tags and "fragile" not in tags:
        return ClaimStatus.REJECTED, f"{obj} 是刚性物体，不易碎"
    return ClaimStatus.UNKNOWN, f"{obj} 易碎性未知"


def _validate_rigid(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    if "rigid" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 是刚性物体"
    return ClaimStatus.UNKNOWN, f"{obj} 刚性未知"


def _validate_sharp(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    tags = world.object_tags.get(obj, set())
    if "sharp" in tags or "weapon" in tags:
        return ClaimStatus.ACCEPTED, f"{obj} 是锐器"
    return ClaimStatus.UNKNOWN, f"{obj} 是否锐利未知"


def _validate_flammable(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    if "flammable" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 可燃"
    return ClaimStatus.UNKNOWN, f"{obj} 可燃性未知"


def _validate_container(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    if "container" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 是容器"
    return ClaimStatus.UNKNOWN, f"{obj} 是否为容器未知"


def _validate_liquid(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj = args[0]
    if "liquid" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 是液体"
    return ClaimStatus.UNKNOWN, f"{obj} 是否为液体未知"


# 5.3 Transformation Claims

_BREAK_CREATES: dict[str, str] = {
    "ale_mug": "glass_shard",
    "bottle": "glass_shard",
}


def _validate_break_creates(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, result = args[0], args[1]
    expected = _BREAK_CREATES.get(obj)
    if expected == result:
        tags = world.object_tags.get(obj, set())
        if "fragile" in tags:
            return ClaimStatus.ACCEPTED, f"{obj} 破碎会产生 {result}"
        return ClaimStatus.INFERRED, f"{obj} 破碎可能产生 {result}"
    return ClaimStatus.UNKNOWN, f"{obj} 破碎是否产生 {result} 未知"


def _validate_spill_creates(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    liquid, result = args[0], args[1]
    tags = world.object_tags.get(liquid, set())
    if "liquid" in tags:
        if result in ("wet_surface", "stain", "spill", "wet"):
            return ClaimStatus.ACCEPTED, f"{liquid} 洒出会产生 {result}"
        return ClaimStatus.INFERRED, f"{liquid} 洒出可能产生 {result}"
    return ClaimStatus.UNKNOWN, f"{liquid} 不是液体"


def _validate_use_as_tool(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, function = args[0], args[1]
    tags = world.object_tags.get(obj, set())
    if function in ("cut", "slash") and ("sharp" in tags or "weapon" in tags):
        return ClaimStatus.ACCEPTED, f"{obj} 可用来切割"
    if function == "wedge" and "rigid" in tags:
        return ClaimStatus.ACCEPTED, f"{obj} 可用来楔入"
    if function == "block" and "rigid" in tags:
        return ClaimStatus.ACCEPTED, f"{obj} 可用来阻挡"
    if function == "throw" and "movable" in tags:
        return ClaimStatus.ACCEPTED, f"{obj} 可投掷"
    return ClaimStatus.UNKNOWN, f"{obj} 是否可用作 {function} 未知"


def _validate_can_block(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, target = args[0], args[1]
    if "rigid" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 可用来阻挡 {target}"
    return ClaimStatus.UNKNOWN, f"{obj} 是否能阻挡未知"


def _validate_can_cut(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    obj, target = args[0], args[1]
    if "sharp" in world.object_tags.get(obj, set()) or "weapon" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 可切割 {target}"
    return ClaimStatus.UNKNOWN, f"{obj} 是否能切割未知"


def _validate_can_throw(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, obj, target = args[0], args[1], args[2]
    if "movable" in world.object_tags.get(obj, set()):
        return ClaimStatus.ACCEPTED, f"{obj} 可投掷向 {target}"
    small = {"loose_stone", "stone", "rock", "stick", "pebble", "mug", "bottle", "glass_shard"}
    if obj in small:
        return ClaimStatus.INFERRED, f"{obj} 看起来可以投掷"
    return ClaimStatus.UNKNOWN, f"{obj} 是否可投掷未知"


# 5.4 Social / Epistemic Claims


def _validate_can_threaten(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, target, means = args[0], args[1], args[2]
    loc_a = _location_of(world, actor)
    loc_b = _location_of(world, target)
    if loc_a != loc_b or not loc_a:
        return ClaimStatus.REJECTED, f"{actor} 和 {target} 不在同一地点"
    if target not in world.npcs and target != "player":
        return ClaimStatus.REJECTED, f"{target} 不是可威胁对象"
    means_tags = world.object_tags.get(means, set())
    if "sharp" in means_tags or "weapon" in means_tags:
        return ClaimStatus.ACCEPTED, f"{means} 可作为威胁手段"
    if means in ("glass_shard", "shard"):
        return ClaimStatus.INFERRED, f"{means} 可作为威胁手段"
    return ClaimStatus.UNKNOWN, f"{means} 是否能威胁未知"


def _validate_can_deceive(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, target = args[0], args[1]
    loc_a = _location_of(world, actor)
    loc_b = _location_of(world, target)
    if loc_a != loc_b or not loc_a:
        return ClaimStatus.REJECTED, f"{actor} 和 {target} 不在同一地点"
    if target not in world.npcs and target != "player":
        return ClaimStatus.REJECTED, f"{target} 不是可欺骗对象"
    return ClaimStatus.ACCEPTED, f"{actor} 可以尝试欺骗 {target}"


def _validate_can_probe_reaction(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, target, topic = args[0], args[1], args[2]
    loc_a = _location_of(world, actor)
    loc_b = _location_of(world, target)
    if loc_a != loc_b or not loc_a:
        return ClaimStatus.REJECTED, f"{actor} 和 {target} 不在同一地点"
    if target not in world.npcs and target != "player":
        return ClaimStatus.REJECTED, f"{target} 不是可观察对象"
    return ClaimStatus.ACCEPTED, f"{actor} 可以观察 {target} 对 {topic} 的反应"


def _validate_topic_sensitive_to(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    target, topic = args[0], args[1]
    for k in world.knowledge:
        if k.agent == target and topic in str(k.fact).lower():
            return ClaimStatus.INFERRED, f"{target} 知道与 {topic} 相关的事"
    for b in world.beliefs.values():
        if target in b.description and topic in b.description:
            return ClaimStatus.PROBABLE, f"{target} 可能与 {topic} 有关"
    return ClaimStatus.UNKNOWN, f"{target} 对 {topic} 的敏感度未知"


def _validate_knows_or_may_know(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    target, topic = args[0], args[1]
    for k in world.knowledge:
        if k.agent == target and topic in str(k.fact).lower():
            return ClaimStatus.ACCEPTED, f"{target} 知道 {topic}"
    for b in world.beliefs.values():
        if target in b.description and topic in b.description:
            return ClaimStatus.INFERRED, f"{target} 可能知道 {topic}"
    return ClaimStatus.UNKNOWN, f"{target} 是否知道 {topic} 未知"


def _validate_reaction_observable(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    actor, target = args[0], args[1]
    loc_a = _location_of(world, actor)
    loc_b = _location_of(world, target)
    if loc_a == loc_b and loc_a:
        return ClaimStatus.ACCEPTED, f"{actor} 可以观察到 {target} 的反应"
    return ClaimStatus.REJECTED, f"{actor} 无法观察 {target}（不同地点）"


# 5.5 Safety / Canon Claims


def _validate_no_absent_entity_direct_action(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    target = args[0]
    if target in world.npcs:
        loc = _location_of(world, target)
        player_loc = _location_of(world, "player")
        if loc == player_loc:
            return ClaimStatus.ACCEPTED, f"{target} 在场"
        return ClaimStatus.REJECTED, f"{target} 不在场"
    return ClaimStatus.ACCEPTED, f"{target} 不是 NPC"


def _validate_impact_within_allowed_bounds(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    effect_desc = args[0]
    high_impact = {"kill", "destroy", "die", "dead", "seal_break", "open", "death"}
    if any(kw in effect_desc.lower() for kw in high_impact):
        return ClaimStatus.UNKNOWN, f"{effect_desc} 可能影响过大，需要审查"
    return ClaimStatus.ACCEPTED, f"{effect_desc} 影响在允许范围内"


# ---------- v0.3.1 hook claim validators ----------


def _validate_hook_active(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    hook_id = args[0]
    hook = world.hooks.get(hook_id)
    if hook and not hook.consumed and hook.ttl > 0:
        return ClaimStatus.ACCEPTED, f"钩子 {hook_id} 活跃"
    return ClaimStatus.REJECTED, f"钩子 {hook_id} 不存在或已过期"


def _validate_owner_has_hook(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    owner, hook_id = args[0], args[1]
    hook = world.hooks.get(hook_id)
    if hook and hook.owner == owner:
        return ClaimStatus.ACCEPTED, f"{owner} 拥有钩子 {hook_id}"
    return ClaimStatus.REJECTED, f"{owner} 不拥有钩子 {hook_id}"


def _validate_player_knows(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    claim_desc = args[0]
    # Check player's knowledge
    for k in world.knowledge:
        if k.agent == "player" and claim_desc in str(k.fact):
            return ClaimStatus.ACCEPTED, f"玩家知道 {claim_desc}"
    # Check if player has witnessed recent events (facts about player)
    for f in world.facts:
        if f.args and f.args[0] == "player" and claim_desc in str(f):
            return ClaimStatus.INFERRED, f"玩家可能知道 {claim_desc}"
    return ClaimStatus.INFERRED, f"玩家可能知道 {claim_desc}（假设亲历）"


def _validate_target_valid_for_hook(world: WorldState, args: tuple[str, ...]) -> tuple[ClaimStatus, str]:
    target, hook_id = args[0], args[1]
    hook = world.hooks.get(hook_id)
    if not hook:
        return ClaimStatus.REJECTED, f"钩子 {hook_id} 不存在"
    if target in hook.valid_targets:
        return ClaimStatus.ACCEPTED, f"{target} 是钩子的有效目标"
    # NPCs are generally valid targets for communicate hooks
    if hook.hook_type == "communicate" and target in world.npcs:
        return ClaimStatus.INFERRED, f"{target} 可以作为沟通目标"
    return ClaimStatus.UNKNOWN, f"{target} 是否有效目标未知"


# ---------- registry ----------

_VALIDATORS: dict[str, Any] = {
    "same_location": _validate_same_location,
    "can_speak_to": _validate_can_speak_to,
    "role_supports": _validate_role_supports,
    "place_supports": _validate_place_supports,
    "item_plausible": _validate_item_plausible,
    "social_tone": _validate_social_tone,
    "topic_plausible_for_place": _validate_topic_plausible_for_place,
    "not_contradicts_locked_fact": _validate_not_contradicts_locked_fact,
    "reachable": _validate_reachable,
    "accessible": _validate_accessible,
    "plausible_scene_object": _validate_plausible_scene_object,
    "movable": _validate_movable,
    "destination_exists": _validate_destination_exists,
    "connected_or_traversable": _validate_connected_or_traversable,
    # v0.3
    "object_exists": _validate_object_exists,
    "object_near": _validate_object_near,
    "has": _validate_has,
    "has_or_near": _validate_has_or_near,
    "can_materialize": _validate_can_materialize,
    "fragile": _validate_fragile,
    "rigid": _validate_rigid,
    "sharp": _validate_sharp,
    "flammable": _validate_flammable,
    "container": _validate_container,
    "liquid": _validate_liquid,
    "break_creates": _validate_break_creates,
    "spill_creates": _validate_spill_creates,
    "use_as_tool": _validate_use_as_tool,
    "can_block": _validate_can_block,
    "can_cut": _validate_can_cut,
    "can_throw": _validate_can_throw,
    "can_threaten": _validate_can_threaten,
    "can_deceive": _validate_can_deceive,
    "can_probe_reaction": _validate_can_probe_reaction,
    "topic_sensitive_to": _validate_topic_sensitive_to,
    "knows_or_may_know": _validate_knows_or_may_know,
    "reaction_observable": _validate_reaction_observable,
    "no_absent_entity_direct_action": _validate_no_absent_entity_direct_action,
    "impact_within_allowed_bounds": _validate_impact_within_allowed_bounds,
    # v0.3.1 hook claims
    "hook_active": _validate_hook_active,
    "owner_has_hook": _validate_owner_has_hook,
    "player_knows": _validate_player_knows,
    "target_valid_for_hook": _validate_target_valid_for_hook,
}


# ---------- utility ----------


def _location_of(world: WorldState, entity: str) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == entity:
            return f.args[1]
    return ""
