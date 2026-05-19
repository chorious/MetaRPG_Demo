"""Dataclasses for the v0.7.0 TurnTransaction pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Operation:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Commitment:
    level: str  # texture, hint, affordance, event, canon, utterance, belief_evidence
    description: str
    operation_index: int = -1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NarrativeFrame:
    beat: str = ""
    active_hooks: list[str] = field(default_factory=list)
    candidate_hints: list[str] = field(default_factory=list)
    motifs_to_use: list[str] = field(default_factory=list)
    dramatic_function: str = ""
    allowed_commitment_levels: list[str] = field(default_factory=list)
    forbidden_moves: list[str] = field(default_factory=list)
    # v0.7.1: L1 ReferenceResolver outputs, consumed by downstream stages
    resolved_targets: list[dict[str, Any]] = field(default_factory=list)
    resolved_props: list[dict[str, Any]] = field(default_factory=list)
    unresolved_mentions: list[str] = field(default_factory=list)
    canonical_id_whitelist: dict[str, list[str]] = field(default_factory=dict)
    # v0.7.2: L2 SemanticJudge hook-relevance results
    semantic_judgments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RenderBrief:
    committed_events: list[str] = field(default_factory=list)
    visible_reactions: list[str] = field(default_factory=list)
    allowed_hints: list[str] = field(default_factory=list)
    motifs_to_render: list[str] = field(default_factory=list)
    style_constraints: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    # v0.7.3: grounding fields for spatial consistency
    player_location: str = ""
    visible_entities: list[str] = field(default_factory=list)
    visible_objects: list[str] = field(default_factory=list)
    absent_entities: list[str] = field(default_factory=list)


@dataclass
class TurnTransaction:
    id: str = ""
    player_input: str = ""
    player_intent: dict[str, Any] = field(default_factory=dict)
    narrative_frame: NarrativeFrame = field(default_factory=NarrativeFrame)
    operations: list[Operation] = field(default_factory=list)
    commitments: list[Commitment] = field(default_factory=list)
    render_brief: RenderBrief = field(default_factory=RenderBrief)
    forbidden_claims: list[str] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationIssue:
    severity: str  # hard_fail, soft_issue
    type: str
    reason: str
    operation_index: int = -1


@dataclass
class DowngradeRecord:
    original_commitment: str
    new_commitment: str
    reason: str
    operation_index: int = -1


@dataclass
class ValidationResult:
    status: str  # accepted, downgraded, rejected
    transaction: TurnTransaction | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    downgrades: list[DowngradeRecord] = field(default_factory=list)
