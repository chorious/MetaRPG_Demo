"""Transaction validator: deterministic core + optional semantic downgrader.

Validator Core enforces hard constraints (item ownership, entity presence,
location reachability, hidden_truth reveal, etc.).
Semantic Downgrader handles nuanced reclassifications (reveal→hint,
canon→utterance) using optional local vLLM assistance.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.transaction import (
    Commitment,
    DowngradeRecord,
    Operation,
    TurnTransaction,
    ValidationIssue,
    ValidationResult,
)
from metarpg.models import WorldState


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_transaction(
    tx: TurnTransaction,
    world: WorldState,
    grammar: dict[str, Any] | None = None,
    client=None,  # local vLLM client for semantic downgrader
) -> ValidationResult:
    """Run full validation on a TurnTransaction.

    Phase 2 MVP: deterministic core only. Semantic downgrader is a
    no-op placeholder until Phase 4+ local vLLM integration is ready.
    """
    issues: list[ValidationIssue] = []
    downgrades: list[DowngradeRecord] = []
    accepted_commitments: list[Commitment] = []

    # 1. Operation-level hard checks
    for i, op in enumerate(tx.operations):
        op_issues = _check_operation(op, i, world)
        issues.extend(op_issues)

    # 2. Commitment-level checks + downgrade paths
    for c in tx.commitments:
        c_issues, c_downgrades, accepted = _check_commitment(
            c, world, grammar, client
        )
        issues.extend(c_issues)
        downgrades.extend(c_downgrades)
        if accepted:
            accepted_commitments.append(accepted)

    # 3. Cross-commitment contradiction
    issues.extend(_check_intra_turn_contradiction(tx, accepted_commitments))

    # 4. Resolve result
    hard_fails = [iss for iss in issues if iss.severity == "hard_fail"]
    if hard_fails:
        return ValidationResult(
            status="rejected", transaction=None, issues=issues, downgrades=downgrades
        )

    status = "downgraded" if downgrades else "accepted"
    validated_tx = TurnTransaction(
        id=tx.id,
        player_input=tx.player_input,
        player_intent=dict(tx.player_intent),
        narrative_frame=tx.narrative_frame,
        operations=list(tx.operations),
        commitments=accepted_commitments,
        render_brief=tx.render_brief,
        forbidden_claims=list(tx.forbidden_claims),
        assumptions=list(tx.assumptions),
    )
    return ValidationResult(
        status=status, transaction=validated_tx, issues=issues, downgrades=downgrades
    )


# ---------------------------------------------------------------------------
# Deterministic Core
# ---------------------------------------------------------------------------


def _check_operation(op: Operation, index: int, world: WorldState) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    kind = op.kind
    params = op.params

    if kind == "extinguish_item" or kind == "consume_item":
        item = params.get("item")
        if not _player_has_item(item, world):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="missing_item",
                    reason=f"Player does not have {item}",
                    operation_index=index,
                )
            )

    elif kind == "speak":
        entity = params.get("entity")
        if not _entity_present(entity, world):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="absent_entity",
                    reason=f"Entity {entity} is not present",
                    operation_index=index,
                )
            )

    elif kind == "move_player":
        destination = params.get("destination")
        if destination and not _location_exists(destination, world):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="unknown_location",
                    reason=f"Location {destination} does not exist",
                    operation_index=index,
                )
            )

    elif kind == "transfer_item":
        item = params.get("item")
        from_entity = params.get("from_entity")
        if from_entity and not _entity_has_item(from_entity, item, world):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="missing_item",
                    reason=f"{from_entity} does not have {item}",
                    operation_index=index,
                )
            )

    elif kind == "update_relation":
        dim = params.get("dim")
        delta = params.get("delta", 0.0)
        if dim and not _relation_delta_in_bounds(delta):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="relation_delta_out_of_bounds",
                    reason=f"Relation delta {delta} out of [-1.0, 1.0] range",
                    operation_index=index,
                )
            )

    elif kind == "update_belief":
        delta = params.get("delta", 0.0)
        if not _belief_delta_in_bounds(delta):
            issues.append(
                ValidationIssue(
                    severity="hard_fail",
                    type="belief_delta_out_of_bounds",
                    reason=f"Belief delta {delta} out of [0.0, 1.0] range",
                    operation_index=index,
                )
            )

    return issues


def _check_commitment(
    c: Commitment,
    world: WorldState,
    grammar: dict[str, Any] | None,
    client,  # noqa: ARG001 — reserved for semantic downgrader
) -> tuple[list[ValidationIssue], list[DowngradeRecord], Commitment | None]:
    """Return (issues, downgrades, accepted_commitment_or_none)."""
    issues: list[ValidationIssue] = []
    downgrades: list[DowngradeRecord] = []

    # Hard check: direct hidden_truth reveal via canon
    if c.level == "canon" and _reveals_hidden_truth(c, world):
        issues.append(
            ValidationIssue(
                severity="hard_fail",
                type="hidden_truth_direct_reveal",
                reason=f"Commitment {c.description!r} directly reveals a hidden truth",
                operation_index=c.operation_index,
            )
        )
        return issues, downgrades, None

    # Deterministic downgrade: canon without evidence → utterance
    if c.level == "canon" and not _has_hard_evidence(c, world):
        downgrades.append(
            DowngradeRecord(
                original_commitment="canon",
                new_commitment="utterance",
                reason="Insufficient hard evidence for canonization",
                operation_index=c.operation_index,
            )
        )
        return issues, downgrades, Commitment(
            level="utterance",
            description=c.description,
            operation_index=c.operation_index,
            metadata=dict(c.metadata),
        )

    # Deterministic downgrade: reveal → hint
    if c.level == "reveal":
        downgrades.append(
            DowngradeRecord(
                original_commitment="reveal",
                new_commitment="hint",
                reason="Reveal always downgraded to hint in v0.7.0 MVP",
                operation_index=c.operation_index,
            )
        )
        return issues, downgrades, Commitment(
            level="hint",
            description=c.description,
            operation_index=c.operation_index,
            metadata=dict(c.metadata),
        )

    # Deterministic downgrade: new_item → texture/affordance
    if c.level == "new_item":
        downgrades.append(
            DowngradeRecord(
                original_commitment="new_item",
                new_commitment="texture",
                reason="New items require explicit world seed; downgraded to texture",
                operation_index=c.operation_index,
            )
        )
        return issues, downgrades, Commitment(
            level="texture",
            description=c.description,
            operation_index=c.operation_index,
            metadata=dict(c.metadata),
        )

    return issues, downgrades, c


def _check_intra_turn_contradiction(
    tx: TurnTransaction, accepted: list[Commitment]
) -> list[ValidationIssue]:
    """Detect operations that contradict each other within the same turn."""
    issues: list[ValidationIssue] = []
    locations: set[str] = set()
    for op in tx.operations:
        if op.kind == "move_player":
            dest = op.params.get("destination")
            if dest in locations:
                issues.append(
                    ValidationIssue(
                        severity="hard_fail",
                        type="intra_turn_contradiction",
                        reason=f"Multiple moves to {dest} in one turn",
                        operation_index=-1,
                    )
                )
            locations.add(dest)
    return issues


# ---------------------------------------------------------------------------
# WorldState helpers
# ---------------------------------------------------------------------------


def _player_has_item(item: str | None, world: WorldState) -> bool:
    if item is None:
        return False
    item_lower = item.lower()
    for fact in world.facts:
        if fact.predicate == "has" and len(fact.args) >= 2:
            if fact.args[0].lower() == "player" and fact.args[1].lower() == item_lower:
                return True
    return False


def _entity_has_item(entity: str, item: str | None, world: WorldState) -> bool:
    if item is None:
        return False
    ent_lower = entity.lower()
    item_lower = item.lower()
    for fact in world.facts:
        if fact.predicate == "has" and len(fact.args) >= 2:
            if fact.args[0].lower() == ent_lower and fact.args[1].lower() == item_lower:
                return True
    return False


def _entity_present(entity: str | None, world: WorldState) -> bool:
    if entity is None:
        return False
    ent_lower = entity.lower()
    if ent_lower == "player":
        return True
    for fact in world.facts:
        if fact.predicate == "at" and len(fact.args) >= 2:
            if fact.args[0].lower() == ent_lower:
                return True
    return False


def _location_exists(location: str | None, world: WorldState) -> bool:
    if location is None:
        return False
    return location in world.locations


def _relation_delta_in_bounds(delta: float) -> bool:
    return -1.0 <= delta <= 1.0


def _belief_delta_in_bounds(delta: float) -> bool:
    return 0.0 <= delta <= 1.0


def _reveals_hidden_truth(commitment: Commitment, world: WorldState) -> bool:
    desc_lower = commitment.description.lower()
    hidden_truths = getattr(world, "hidden_truths", {})
    if not isinstance(hidden_truths, dict):
        return False
    for ht in hidden_truths.values():
        aliases: list[str] = []
        if isinstance(ht, dict):
            aliases = ht.get("aliases", [])
        elif hasattr(ht, "aliases"):
            aliases = list(ht.aliases) if not isinstance(ht.aliases, str) else [ht.aliases]
        for alias in aliases:
            if alias.lower() in desc_lower:
                return True
    return False


def _has_hard_evidence(commitment: Commitment, world: WorldState) -> bool:
    """Placeholder: in MVP, only explicit canon_facts count as hard evidence."""
    desc_lower = commitment.description.lower()
    for fact in world.facts:
        if desc_lower in str(fact).lower():
            return True
    return False
