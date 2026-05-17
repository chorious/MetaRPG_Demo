"""Patch assembler — turn a validated ActHypothesis into a Patch.

Only effects whose support claims pass required thresholds become canon.
The assembler also converts support claims into patch requirements.

v0.3 adds:
  - Composite act support (subacts evaluated independently, partial success)
  - Effect-kind-specific admission rules (not just impact tiers)
  - New effect kinds: canon_event, add_object, remove_object, attention_delta, risk_flag
"""
from __future__ import annotations

from .claims import validate_hypothesis_support_claims
from .models import ActHypothesis, ClaimStatus, Effect, Patch, ProposedEffect, ValidationResult, WorldState
from .rules import validate_patch


# Core claims whose rejection blocks social+ effects and movement
_CORE_CLAIMS = {
    "same_location", "can_speak_to", "role_supports", "place_supports",
    "accessible", "destination_exists", "connected_or_traversable",
}

# v0.3 social-level claims
_V3_SOCIAL_CLAIMS = _CORE_CLAIMS | {
    "no_absent_entity_direct_action", "can_threaten", "can_deceive",
    "can_probe_reaction", "reaction_observable",
}

_STATUS_RANK = {
    ClaimStatus.ACCEPTED: 4,
    ClaimStatus.INFERRED: 3,
    ClaimStatus.PROBABLE: 2,
    ClaimStatus.UNKNOWN: 1,
    ClaimStatus.REJECTED: 0,
}


def assemble_patch(hypothesis: ActHypothesis, world: WorldState) -> Patch:
    """Turn a hypothesis into a Patch, filtering effects by claim validation.

    For composite acts (subacts present), each subact is evaluated independently.
    Partial success is supported: some subacts may pass while others are rejected.
    """
    if hypothesis.subacts:
        return _assemble_composite(hypothesis, world)
    return _assemble_flat(hypothesis, world)


def _assemble_flat(hypothesis: ActHypothesis, world: WorldState) -> Patch:
    """v0.2-style flat hypothesis assembly."""
    requirements = _collect_requirements(hypothesis.support_claims)
    min_core_status = _min_core_status(hypothesis.support_claims)

    accepted_effects: list[Effect] = []
    for pe in hypothesis.intended_effects:
        ok, reason = _effect_allowed(pe, hypothesis.support_claims)
        if not ok:
            continue
        kind = _maybe_downgrade_event(pe.kind, min_core_status, pe.impact)
        accepted_effects.append(Effect(kind=kind, payload=pe.payload))

    return Patch(
        intent=_build_intent(hypothesis),
        requirements=requirements,
        effects=accepted_effects,
    )


def _assemble_composite(hypothesis: ActHypothesis, world: WorldState) -> Patch:
    """v0.3 composite act: evaluate each subact independently."""
    all_effects: list[Effect] = []
    all_requirements: list[str] = []

    # Evaluate top-level claims + effects
    top_claims = hypothesis.support_claims
    all_requirements.extend(_collect_requirements(top_claims))
    top_min_core = _min_core_status(top_claims)
    for pe in hypothesis.intended_effects:
        ok, _ = _effect_allowed(pe, top_claims)
        if ok:
            kind = _maybe_downgrade_event(pe.kind, top_min_core, pe.impact)
            all_effects.append(Effect(kind=kind, payload=pe.payload))

    # Evaluate each subact independently
    for subact in hypothesis.subacts:
        sub_claims = validate_hypothesis_support_claims(world, subact.claims)
        sub_min_core = _min_core_status(sub_claims)
        all_requirements.extend(_collect_requirements(sub_claims))

        for pe in subact.effects:
            ok, _ = _effect_allowed(pe, sub_claims)
            if ok:
                kind = _maybe_downgrade_event(pe.kind, sub_min_core, pe.impact)
                all_effects.append(Effect(kind=kind, payload=pe.payload))

    # Deduplicate requirements
    seen: set[str] = set()
    deduped_reqs: list[str] = []
    for r in all_requirements:
        if r not in seen:
            seen.add(r)
            deduped_reqs.append(r)

    return Patch(
        intent=_build_intent(hypothesis),
        requirements=deduped_reqs,
        effects=all_effects,
    )


def _collect_requirements(claims: list) -> list[str]:
    """Extract patch requirements from ACCEPTED/INFERRED claims."""
    reqs: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        if claim.status in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED):
            req = _claim_to_requirement(claim)
            if req and req not in seen:
                seen.add(req)
                reqs.append(req)
    return reqs


def _min_core_status(claims: list) -> ClaimStatus:
    """Lowest status among core claims; ACCEPTED if none present."""
    present_core = [c for c in claims if c.name in _CORE_CLAIMS]
    if not present_core:
        return ClaimStatus.ACCEPTED
    return min(present_core, key=lambda c: _STATUS_RANK.get(c.status, 0)).status


def _maybe_downgrade_event(kind: str, min_core_status: ClaimStatus, impact: int) -> str:
    """v0.2.1: UNKNOWN core claims downgrade events to transient_event."""
    if kind == "event" and min_core_status == ClaimStatus.UNKNOWN:
        return "transient_event"
    if kind == "event" and min_core_status == ClaimStatus.PROBABLE and impact == 0:
        # PROBABLE supports narration but not hard canon
        pass
    return kind


def _build_intent(hypothesis: ActHypothesis) -> str:
    return f"{hypothesis.act_kind}(player,{hypothesis.target or ''},{hypothesis.topic or ''})"


# ---------- effect admission ----------


def _effect_allowed(pe: ProposedEffect, claims: list) -> tuple[bool, str]:
    """Check if a proposed effect is allowed given claim validation statuses.

    v0.3 adds effect-kind-specific rules on top of impact-tier logic.
    """
    kind = pe.kind
    statuses = {c.name: c.status for c in claims}

    # --- v0.3 effect-kind-specific rules ---

    if kind == "transient_event":
        # Transient events are narration-only; always allowed unless contradicted
        return True, ""

    if kind == "canon_event":
        # Requires no REJECTED social claims + at least one strong social claim
        present_social = [c for c in claims if c.name in _V3_SOCIAL_CLAIMS]
        has_rejected = any(c.status == ClaimStatus.REJECTED for c in present_social)
        if has_rejected:
            return False, "社交声明被拒绝，无法产生正典事件"
        has_strong = any(
            c.status in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED)
            for c in present_social
        )
        if present_social and not has_strong:
            return False, "没有强社交声明支持正典事件"
        return True, ""

    if kind == "add_object":
        # Requires plausible_scene_object or can_materialize or item_plausible
        pm = statuses.get("plausible_scene_object")
        cm = statuses.get("can_materialize")
        ip = statuses.get("item_plausible")
        if any(s in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED, ClaimStatus.PROBABLE) for s in (pm, cm, ip) if s):
            return True, ""
        return False, "物体物质化缺乏合理性支持"

    if kind == "remove_object":
        has_s = statuses.get("has")
        on = statuses.get("object_near")
        if has_s == ClaimStatus.ACCEPTED or on == ClaimStatus.ACCEPTED:
            return True, ""
        return False, "无法移除不在场的物体"

    if kind == "rel_delta":
        # v0.3: requires same_location, can_speak_to, or no_absent_entity
        sl = statuses.get("same_location")
        cst = statuses.get("can_speak_to")
        naeda = statuses.get("no_absent_entity_direct_action")
        if any(s in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED) for s in (sl, cst, naeda) if s):
            return True, ""
        # Fallback to impact-based logic for backward compatibility
        return _effect_allowed_by_impact(pe, claims)

    if kind == "belief_delta":
        # v0.3: can_probe_reaction or reaction_observable enables belief updates
        cpr = statuses.get("can_probe_reaction")
        ro = statuses.get("reaction_observable")
        if any(s in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED) for s in (cpr, ro) if s):
            return True, ""
        # Fallback to impact-based logic
        return _effect_allowed_by_impact(pe, claims)

    if kind in ("attention_delta", "risk_flag"):
        # Social tier
        return _effect_allowed_by_impact(pe, claims)

    # --- Default: impact-based logic (v0.2) ---
    return _effect_allowed_by_impact(pe, claims)


def _effect_allowed_by_impact(pe: ProposedEffect, claims: list) -> tuple[bool, str]:
    """v0.2 impact-tier admission control."""
    statuses = {c.name: c.status for c in claims}

    present_core = [cn for cn in _CORE_CLAIMS if cn in statuses]
    has_rejected_core = any(
        statuses.get(cn) == ClaimStatus.REJECTED for cn in present_core
    )
    all_core_strong = all(
        statuses.get(cn) in (ClaimStatus.ACCEPTED, ClaimStatus.INFERRED)
        for cn in present_core
    ) if present_core else True
    all_core_accepted = all(
        statuses.get(cn) == ClaimStatus.ACCEPTED
        for cn in present_core
    ) if present_core else True

    if pe.impact == 0:
        return True, ""

    if pe.impact == 1:
        if has_rejected_core:
            return False, "核心声明被拒绝"
        return True, ""

    if pe.impact == 2:
        if not all_core_strong:
            return False, "核心声明不够强（需要已确认或已推断）"
        return True, ""

    if pe.impact == 3:
        if not all_core_accepted:
            return False, "核心声明未完全确认"
        return True, ""

    return True, ""


# ---------- requirement conversion ----------


def _claim_to_requirement(claim) -> str | None:
    """Convert a validated claim into a patch REQUIRES string."""
    if claim.name == "same_location":
        return f"same_location({claim.args[0]},{claim.args[1]})"
    if claim.name == "can_speak_to":
        return f"same_location({claim.args[0]},{claim.args[1]})"
    if claim.name == "accessible":
        return f"accessible({claim.args[0]})"
    if claim.name == "not_contradicts_locked_fact":
        return None
    # v0.3: additional claims that become requirements
    if claim.name == "no_absent_entity_direct_action":
        return None  # This is a safety check, not a runtime requirement
    return None
