"""Hook lifecycle management — v0.3.1.

Ticks, consumes, merges, and queries EventHooks.
"""
from __future__ import annotations

from .models import EventHook, WorldState


def tick_hooks(world: WorldState) -> list[str]:
    """Decay ttl for all active hooks. Returns list of expired hook ids."""
    expired: list[str] = []
    for hook in list(world.hooks.values()):
        if hook.consumed:
            continue
        if hook.decay_policy == "decay_each_turn":
            hook.ttl -= 1
            if hook.ttl <= 0:
                expired.append(hook.id)
        elif hook.decay_policy == "consume_once":
            # Don't auto-decay; wait for consumption
            pass
    for hid in expired:
        if hid in world.hooks:
            del world.hooks[hid]
    return expired


def consume_hook(world: WorldState, hook_id: str) -> bool:
    """Mark a hook as consumed. Returns True if found and not already consumed."""
    hook = world.hooks.get(hook_id)
    if hook and not hook.consumed:
        hook.consumed = True
        if hook.decay_policy == "consume_once":
            del world.hooks[hook_id]
        return True
    return False


def decay_hook(world: WorldState, hook_id: str, amount: int = 1) -> bool:
    """Reduce a hook's ttl by amount. Returns True if hook still active."""
    hook = world.hooks.get(hook_id)
    if not hook or hook.consumed:
        return False
    hook.ttl -= amount
    if hook.ttl <= 0:
        del world.hooks[hook_id]
        return False
    return True


def is_hook_active(hook: EventHook) -> bool:
    """Check if a hook is available for matching."""
    return not hook.consumed and hook.ttl > 0


def get_active_hooks(world: WorldState, owner: str = "player") -> list[EventHook]:
    """Return all active hooks owned by the given actor."""
    return [
        h for h in world.hooks.values()
        if is_hook_active(h) and h.owner == owner
    ]


def merge_similar_hooks(world: WorldState) -> list[str]:
    """Merge communicate hooks that share owner, topics, and targets.

    Returns list of merged hook ids.
    """
    groups: dict[tuple[str, str, frozenset[str]], list[EventHook]] = {}
    for hook in list(world.hooks.values()):
        if hook.consumed:
            continue
        key = (hook.owner, hook.hook_type, frozenset(hook.topics))
        groups.setdefault(key, []).append(hook)

    merged_ids: list[str] = []
    for group in groups.values():
        if len(group) <= 1:
            continue
        # Pick highest priority hook as base
        base = max(group, key=lambda h: h.priority)
        for hook in group:
            if hook.id == base.id:
                continue
            # Merge fields
            base.source_events = list(set(base.source_events) | set(hook.source_events))
            base.trigger_cues = list(set(base.trigger_cues) | set(hook.trigger_cues))
            base.valid_targets = list(set(base.valid_targets) | set(hook.valid_targets))
            base.payload_claims.extend(hook.payload_claims)
            base.proposed_effects.extend(hook.proposed_effects)
            base.participants = list(set(base.participants) | set(hook.participants))
            base.places = list(set(base.places) | set(hook.places))
            base.priority = min(1.0, base.priority + 0.1)
            base.ttl = max(base.ttl, hook.ttl)
            del world.hooks[hook.id]
            merged_ids.append(hook.id)
    return merged_ids
