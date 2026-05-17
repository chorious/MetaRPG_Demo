"""Hook matching — v0.3.1.

Matches active EventHooks against MetaActs.
"""
from __future__ import annotations

from .hooks import get_active_hooks, is_hook_active
from .models import ActHypothesis, Claim, ClaimStatus, EventHook, MetaAct, ProposedEffect, WorldState


# Cues that strongly suggest hook-trigger intent
_HOOK_TRIGGER_CUES: set[str] = {
    "刚才", "刚刚", "情形", "告诉", "说给", "提起",
    "那件事", "之前", "刚才的", "发生的事",
    "刚才", "tell", "mentioned", "what happened", "earlier",
}


def match_active_hooks(meta: MetaAct, world: WorldState, owner: str = "player") -> tuple[EventHook | None, float]:
    """Match active hooks against a MetaAct.

    Returns (best_matched_hook, confidence_score) or (None, 0.0).
    """
    text = meta.raw_text
    loc = meta.player_location
    nearby = set(meta.local_entities)

    best_hook: EventHook | None = None
    best_score = 0.0

    for hook in get_active_hooks(world, owner):
        score = _score_hook_match(hook, text, loc, nearby, meta)
        if score > best_score and score >= 0.45:
            best_score = score
            best_hook = hook

    return best_hook, best_score


def _score_hook_match(hook: EventHook, text: str, loc: str, nearby: set[str], meta: MetaAct) -> float:
    """Score how well a hook matches the current MetaAct. 0.0–1.0."""
    score = 0.0
    text_lower = text.lower()

    # Cue overlap (strongest signal)
    matched_cues = sum(1 for c in hook.trigger_cues if c.lower() in text_lower)
    if matched_cues > 0:
        score += min(0.5, matched_cues * 0.15)

    # Generic hook-trigger cues boost score
    if any(c in text for c in _HOOK_TRIGGER_CUES):
        score += 0.15

    # Target match: is the intended recipient present?
    for target in hook.valid_targets:
        if target in nearby:
            score += 0.2
            break

    # Topic overlap
    for topic in hook.topics:
        if topic.lower() in text_lower:
            score += 0.08

    # Place match
    for place in hook.places:
        if place == loc:
            score += 0.05

    # Recency bonus
    turn_diff = meta.turn - hook.source_turn
    if turn_diff <= 2:
        score += 0.1
    elif turn_diff <= 5:
        score += 0.05

    # Priority boost
    score += hook.priority * 0.15

    return min(1.0, score)


def build_hook_hypothesis(hook: EventHook, meta: MetaAct, world: WorldState) -> ActHypothesis:
    """Build an ActHypothesis from a matched EventHook."""
    target = _infer_target_from_hook(hook, meta)
    loc = meta.player_location

    # Build support claims
    support_claims: list[Claim] = [
        Claim("hook_active", (hook.id,), ClaimStatus.UNKNOWN, "待验证"),
        Claim("same_location", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
        Claim("can_speak_to", ("player", target), ClaimStatus.UNKNOWN, "待验证"),
    ]

    # Payload claims: player knows / witnessed the events
    for ev in hook.source_events:
        support_claims.append(
            Claim("player_knows", (ev,), ClaimStatus.UNKNOWN, "hook payload")
        )

    # Target validity
    support_claims.append(
        Claim("target_valid_for_hook", (target, hook.id), ClaimStatus.UNKNOWN, "待验证")
    )

    # Build intended effects from hook + consume
    intended_effects: list[ProposedEffect] = list(hook.proposed_effects)
    intended_effects.append(ProposedEffect("consume_hook", (hook.id,), 0))

    # Also add an event for narration
    event_name = f"player_told_{target}_about_{hook.topics[0] if hook.topics else 'something'}"
    intended_effects.append(ProposedEffect("canon_event", (event_name,), 1))

    confidence = min(0.92, 0.55 + hook.priority * 0.35)
    if any(c in meta.raw_text for c in {"刚才", "刚刚", "情形", "tell"}):
        confidence = min(0.95, confidence + 0.08)

    return ActHypothesis(
        act_kind="trigger_event_hook",
        confidence=confidence,
        support_claims=support_claims,
        intended_effects=intended_effects,
        raw_text=meta.raw_text,
        target=target,
        topic=hook.topics[0] if hook.topics else "",
    )


def _infer_target_from_hook(hook: EventHook, meta: MetaAct) -> str:
    """Infer the target entity from hook valid_targets and MetaAct context."""
    nearby = set(meta.local_entities)
    # Prefer a valid target that is present
    for t in hook.valid_targets:
        if t in nearby:
            return t
    # Fallback: first valid target or first nearby NPC
    if hook.valid_targets:
        return hook.valid_targets[0]
    if meta.local_entities:
        return meta.local_entities[0]
    return "scene"
