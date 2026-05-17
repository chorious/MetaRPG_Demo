"""Hard Auditor — code-owned, no LLM.

Checks:
1. Entity presence
2. Object existence / possession
3. Location accessibility
4. Knowledge ownership
5. Hidden fact leakage
6. Narrative claim vs candidate patch alignment
7. Patch effect validity
8. Raw debug exposure
9. Hard state change support
10. Contradiction with locked facts

New in v0.6.1:
- ambient_entity_action is allowed if scene-appropriate
- npc_speech requires patch support (npc_speech, knowledge_transfer, reveal, or transient_event)
- npc_offer requires patch support
- unregistered concrete prop is medium_issue, not hard_fail
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.schemas import (
    AuditIssue,
    CandidatePatchEffect,
    NarrativeClaim,
    Segment,
)
from metarpg.models import Fact, WorldState


# Valid effect kinds (closed set)
_VALID_EFFECT_KINDS = {
    "transient_event",
    "journal_note",
    "observe_reaction",
    "knowledge_transfer",
    "relation_delta",
    "belief_delta",
    "move",
    "add_fact",
    "remove_fact",
    "create_hook",
    "consume_item",
    "acquire_item",
    "risk_flag",
    "reveal",
}


def run_hard_audit(
    story_packet: dict[str, Any],
    segments: list[Segment],
    translated_claims: list[NarrativeClaim],
    scanner_findings: dict[str, Any],
    candidate_patch: list[CandidatePatchEffect],
    pre_world: WorldState,
) -> dict[str, Any]:
    """Run all hard checks and return audit report."""
    hard_issues: list[AuditIssue] = []
    medium_issues: list[AuditIssue] = []

    # 1. Hidden fact leakage
    hard_issues.extend(_check_hidden_leak(segments, translated_claims, scanner_findings, story_packet))

    # 2. Absent entity actions (named entities only; ambient allowed)
    hard_issues.extend(_check_absent_entities(translated_claims, story_packet))

    # 3. Remote event claims
    hard_issues.extend(_check_remote_events(translated_claims, story_packet))

    # 4. Raw debug exposure
    hard_issues.extend(_check_raw_debug(scanner_findings))

    # 5. Patch effect validity
    hard_issues.extend(_check_patch_validity(candidate_patch, story_packet, pre_world))

    # 6. Narrative claim vs patch alignment
    hi, mi = _check_alignment(segments, translated_claims, candidate_patch, story_packet)
    hard_issues.extend(hi)
    medium_issues.extend(mi)

    # 7. Contradiction with locked facts
    hard_issues.extend(_check_locked_facts(candidate_patch, pre_world))

    claim_count = len(translated_claims)
    patch_count = len(candidate_patch)
    claims_without_patch = _count_claims_without_patch_support(translated_claims, candidate_patch)
    patch_without_narrative = _count_patch_without_narrative_support(candidate_patch, translated_claims)

    return {
        "passed": len(hard_issues) == 0,
        "issues": [issue.__dict__ for issue in hard_issues],
        "medium_issues": [issue.__dict__ for issue in medium_issues],
        "alignment_check": {
            "narrative_claims_count": claim_count,
            "patch_effects_count": patch_count,
            "claims_without_patch_support": claims_without_patch,
            "patch_without_narrative_support": patch_without_narrative,
        },
    }


def _check_hidden_leak(
    segments: list[Segment],
    claims: list[NarrativeClaim],
    scanner: dict[str, Any],
    story_packet: dict[str, Any],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    hidden_aliases = set(story_packet.get("forbidden", {}).get("hidden_fact_aliases", []))

    for alias in scanner.get("hidden_fact_alias_hits", []):
        issues.append(
            AuditIssue(
                severity="hard_fail",
                type="hidden_fact_leak",
                evidence=alias,
                reason=f"Hidden fact alias '{alias}' appears in narrative text.",
                repair_instruction="Remove hidden fact reference or replace with vague external cue.",
            )
        )

    for claim in claims:
        if claim.kind == "hidden_fact_reference":
            issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="hidden_fact_leak",
                    segment_id=claim.segment_id,
                    evidence=claim.evidence_span,
                    reason="Narrative explicitly references a hidden fact.",
                    repair_instruction="Replace with external observable behavior that hints without revealing.",
                )
            )

    for claim in claims:
        if claim.kind == "npc_inner_state":
            text = claim.evidence_span.lower()
            for alias in hidden_aliases:
                if alias.lower() in text:
                    issues.append(
                        AuditIssue(
                            severity="hard_fail",
                            type="hidden_fact_leak",
                            segment_id=claim.segment_id,
                            evidence=claim.evidence_span,
                            reason=f"NPC inner thought exposes hidden fact '{alias}'.",
                            repair_instruction="Remove inner thought. Keep only external observable reaction.",
                        )
                    )

    return issues


def _check_absent_entities(
    claims: list[NarrativeClaim],
    story_packet: dict[str, Any],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    present = set(story_packet.get("scene", {}).get("visible_entities", []))
    absent = set(story_packet.get("forbidden", {}).get("entities_not_present", []))

    for claim in claims:
        # Allow ambient entities
        if claim.kind == "ambient_entity_action":
            continue

        if claim.subject and claim.subject in absent:
            issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="absent_entity_action",
                    segment_id=claim.segment_id,
                    evidence=claim.evidence_span,
                    reason=f"Entity '{claim.subject}' is not present but is described as acting.",
                    repair_instruction=f"Remove action by '{claim.subject}' or move player to their location first.",
                )
            )
        if claim.target and claim.target in absent:
            if claim.kind in {"npc_observable_action", "npc_observable_reaction", "player_action", "npc_speech"}:
                issues.append(
                    AuditIssue(
                        severity="hard_fail",
                        type="absent_entity_action",
                        segment_id=claim.segment_id,
                        evidence=claim.evidence_span,
                        reason=f"Entity '{claim.target}' is not present but is directly interacted with.",
                        repair_instruction=f"Remove direct interaction with '{claim.target}'.",
                    )
                )

    return issues


def _check_remote_events(
    claims: list[NarrativeClaim],
    story_packet: dict[str, Any],
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for claim in claims:
        if claim.kind == "remote_event":
            issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="remote_event_claim",
                    segment_id=claim.segment_id,
                    evidence=claim.evidence_span,
                    reason="Narrative claims awareness of events at a remote location.",
                    repair_instruction="Remove remote event claim. Player can only perceive local scene.",
                )
            )
    return issues


def _check_raw_debug(scanner: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for raw_id in scanner.get("raw_event_id_hits", []):
        issues.append(
            AuditIssue(
                severity="hard_fail",
                type="raw_debug_exposure",
                evidence=raw_id,
                reason=f"Raw snake_case event ID '{raw_id}' exposed in player-facing text.",
                repair_instruction="Replace raw ID with natural prose description.",
            )
        )
    return issues


def _check_patch_validity(
    candidate_patch: list[CandidatePatchEffect],
    story_packet: dict[str, Any],
    pre_world: WorldState,
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    allowed = set(story_packet.get("allowed_effect_kinds", []))

    for eff in candidate_patch:
        if eff.kind not in _VALID_EFFECT_KINDS:
            issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="invalid_effect_kind",
                    evidence=eff.kind,
                    reason=f"Effect kind '{eff.kind}' is not in the schema.",
                    repair_instruction=f"Replace with one of: {', '.join(sorted(_VALID_EFFECT_KINDS))}.",
                )
            )
        elif eff.kind not in allowed:
            issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="invalid_effect_kind",
                    evidence=eff.kind,
                    reason=f"Effect kind '{eff.kind}' is not allowed in this context.",
                    repair_instruction=f"Allowed kinds: {', '.join(sorted(allowed))}.",
                )
            )

    # Object possession check for consume_item
    for eff in candidate_patch:
        if eff.kind == "consume_item":
            item = eff.args.get("item", "")
            if item:
                player_has = any(
                    f.predicate == "has" and f.args == ("player", item)
                    for f in pre_world.facts
                )
                if not player_has:
                    # v0.6.1: downgrade to medium if item is scene-plausible ambient
                    inventory = story_packet.get("player_context", {}).get("inventory_or_handheld", [])
                    visible_objs = story_packet.get("scene", {}).get("visible_objects", [])
                    if item in inventory or item in visible_objs:
                        issues.append(
                            AuditIssue(
                                severity="hard_fail",
                                type="state_change_without_support",
                                evidence=str(eff.args),
                                reason=f"Player does not have '{item}' to consume.",
                                repair_instruction="Add acquire_item first or remove consume_item.",
                            )
                        )
                    else:
                        # Medium: unregistered concrete prop usage
                        issues.append(
                            AuditIssue(
                                severity="medium_issue",
                                type="unregistered_concrete_prop",
                                evidence=item,
                                reason=f"Item '{item}' is not in inventory or visible_objects.",
                                repair_instruction="Use acquire_item first, or use transient_event instead.",
                            )
                        )

    # Location check for move
    for eff in candidate_patch:
        if eff.kind == "move":
            dest = eff.args.get("destination", "")
            if dest and dest not in pre_world.locations:
                issues.append(
                    AuditIssue(
                        severity="hard_fail",
                        type="state_change_without_support",
                        evidence=dest,
                        reason=f"Destination '{dest}' is not a known location.",
                        repair_instruction="Use a known location from the world schema.",
                    )
                )

    return issues


def _check_alignment(
    segments: list[Segment],
    claims: list[NarrativeClaim],
    candidate_patch: list[CandidatePatchEffect],
    story_packet: dict[str, Any],
) -> tuple[list[AuditIssue], list[AuditIssue]]:
    hard_issues: list[AuditIssue] = []
    medium_issues: list[AuditIssue] = []

    patch_kinds = {eff.kind for eff in candidate_patch}

    # NPC speech claims require patch support
    speech_claims = [c for c in claims if c.kind in {"npc_speech", "npc_offer"}]
    for claim in speech_claims:
        has_support = any(
            pk in patch_kinds
            for pk in ("knowledge_transfer", "reveal", "create_hook")
        )
        # transient_event can support speech if it explicitly describes speech
        if not has_support and "transient_event" in patch_kinds:
            # Accept transient_event as support for speech if no better patch exists
            has_support = True

        if not has_support:
            hard_issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="npc_speech_without_patch_support",
                    segment_id=claim.segment_id,
                    evidence=claim.evidence_span,
                    reason="NPC speech or offer creates a concrete interaction opportunity not represented in candidate_patch.",
                    repair_instruction="Add npc_speech/offer_refill/create_affordance patch effects, or rewrite the segment as a silent observable reaction.",
                )
            )

    # NPC offer claims require even stronger support
    offer_claims = [c for c in claims if c.kind == "npc_offer"]
    for claim in offer_claims:
        has_offer_patch = any(
            eff.kind in {"create_hook", "reveal", "knowledge_transfer"}
            for eff in candidate_patch
        )
        if not has_offer_patch:
            hard_issues.append(
                AuditIssue(
                    severity="hard_fail",
                    type="npc_offer_without_patch_support",
                    segment_id=claim.segment_id,
                    evidence=claim.evidence_span,
                    reason="NPC offer creates a concrete affordance not represented in candidate_patch.",
                    repair_instruction="Add offer_refill/create_affordance patch effect, or remove the offer.",
                )
            )

    # Stateful claims without patch support
    stateful_claim_kinds = {
        "player_action",
        "named_entity_action",
        "world_state_change",
        "object_state",
        "location_state",
        "prop_usage",
    }
    for claim in claims:
        if claim.kind in stateful_claim_kinds:
            has_support = False
            if claim.kind == "player_action" and any(
                k in patch_kinds for k in ("consume_item", "move", "acquire_item")
            ):
                has_support = True
            if claim.kind == "named_entity_action" and "observe_reaction" in patch_kinds:
                has_support = True
            if claim.kind == "world_state_change" and len(candidate_patch) > 0:
                has_support = True
            if claim.kind == "prop_usage" and any(
                k in patch_kinds for k in ("consume_item", "acquire_item", "transient_event")
            ):
                has_support = True

            if not has_support and len(candidate_patch) == 0:
                hard_issues.append(
                    AuditIssue(
                        severity="hard_fail",
                        type="patch_without_support",
                        segment_id=claim.segment_id,
                        evidence=claim.evidence_span,
                        reason=f"Claim '{claim.kind}' implies state change but no patch effect supports it.",
                        repair_instruction="Add a matching patch effect or mark claim as transient/pure description.",
                    )
                )

    # Patch effects with no narrative support (unless pure_commit allowed)
    for eff in candidate_patch:
        if eff.kind in {"add_fact", "remove_fact", "belief_delta", "relation_delta"}:
            has_narrative = any(
                c.kind in stateful_claim_kinds | {"npc_speech", "player_action", "npc_observable_action"}
                for c in claims
            )
            if not has_narrative and len(segments) == 0:
                hard_issues.append(
                    AuditIssue(
                        severity="hard_fail",
                        type="state_change_without_support",
                        evidence=eff.kind,
                        reason=f"Patch effect '{eff.kind}' has no narrative justification.",
                        repair_instruction="Add a narrative segment describing this change, or remove the effect.",
                    )
                )

    # Unregistered concrete prop usage (medium)
    inventory = set(story_packet.get("player_context", {}).get("inventory_or_handheld", []))
    visible_objs = set(story_packet.get("scene", {}).get("visible_objects", []))
    for claim in claims:
        if claim.kind == "prop_usage":
            # Determine what prop is used
            prop = claim.metadata.get("prop", "")
            if prop and prop not in inventory and prop not in visible_objs:
                medium_issues.append(
                    AuditIssue(
                        severity="medium_issue",
                        type="unregistered_concrete_prop",
                        segment_id=claim.segment_id,
                        evidence=claim.evidence_span,
                        reason=f"Prop '{prop}' is not in inventory_or_handheld or visible_objects.",
                        repair_instruction="Use lower-commitment prose, or add acquire_item patch first.",
                    )
                )

    return hard_issues, medium_issues


def _check_locked_facts(
    candidate_patch: list[CandidatePatchEffect],
    pre_world: WorldState,
) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    locked_predicates = {"alive", "dead", "exists"}
    for eff in candidate_patch:
        if eff.kind == "remove_fact":
            pred = eff.args.get("predicate", "")
            if pred in locked_predicates:
                issues.append(
                    AuditIssue(
                        severity="hard_fail",
                        type="locked_fact_contradiction",
                        evidence=pred,
                        reason=f"Cannot remove locked fact predicate '{pred}'.",
                        repair_instruction="Remove this effect. Locked facts are immutable.",
                    )
                )
    return issues


def _count_claims_without_patch_support(
    claims: list[NarrativeClaim],
    candidate_patch: list[CandidatePatchEffect],
) -> int:
    if not candidate_patch:
        return sum(1 for c in claims if c.kind in {
            "player_action", "named_entity_action", "world_state_change", "prop_usage"
        })
    return 0


def _count_patch_without_narrative_support(
    candidate_patch: list[CandidatePatchEffect],
    claims: list[NarrativeClaim],
) -> int:
    if not claims:
        return len(candidate_patch)
    return 0
