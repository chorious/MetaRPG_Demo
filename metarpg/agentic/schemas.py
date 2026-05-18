"""Core dataclasses for the agentic pipeline.

TurnDraft is the central object that records the full lifecycle of one turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Segment — one piece of player-facing narrative
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    id: str
    type: str  # player_action, npc_observable_reaction, etc.
    text: str
    patch_refs: list[str] = field(default_factory=list)
    declared_claims: list[str] = field(default_factory=list)
    transient_only: bool = False  # if true, this segment has no patch_refs


# ---------------------------------------------------------------------------
# Candidate Patch Effect — proposed world change
# ---------------------------------------------------------------------------

@dataclass
class CandidatePatchEffect:
    kind: str
    args: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Narrative Claim — extracted by Translator
# ---------------------------------------------------------------------------

@dataclass
class NarrativeClaim:
    segment_id: str
    kind: str  # npc_observable_action, hidden_fact_reference, etc.
    subject: str | None = None
    action: str | None = None
    target: str | None = None
    evidence_span: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Audit Issue — from Hard or Soft Auditor
# ---------------------------------------------------------------------------

@dataclass
class AuditIssue:
    severity: str  # hard_fail, soft_issue
    type: str  # hidden_fact_leak, absent_entity_action, too_mechanical, etc.
    segment_id: str | None = None
    evidence: str = ""
    reason: str = ""
    repair_instruction: str = ""


# ---------------------------------------------------------------------------
# Rewrite Task — from Editor
# ---------------------------------------------------------------------------

@dataclass
class RewriteTask:
    segment_id: str
    operation: str  # replace, delete, insert_after
    severity: str
    reason: str
    keep_context_segments: list[str] = field(default_factory=list)
    allowed_patch_refs: list[str] = field(default_factory=list)
    instruction: str = ""


# ---------------------------------------------------------------------------
# Feasibility Report — lightweight pre-check on player input
# ---------------------------------------------------------------------------

@dataclass
class FeasibilityReport:
    feasibility_facts: list[str] = field(default_factory=list)
    preserve_player_voice: list[str] = field(default_factory=list)
    world_response_kind: str = "accept"  # absence | friction | reframing | accept
    stated_action: str = ""
    stated_props: list[str] = field(default_factory=list)
    stated_targets: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Writer Output
# ---------------------------------------------------------------------------

@dataclass
class WriterOutput:
    interpretation: str = ""
    segments: list[Segment] = field(default_factory=list)
    candidate_patch: list[CandidatePatchEffect] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Story Packet — compact local context fed to agents
# ---------------------------------------------------------------------------

@dataclass
class StoryPacket:
    scene: dict[str, Any] = field(default_factory=dict)
    player_context: dict[str, Any] = field(default_factory=dict)
    npc_surface: dict[str, Any] = field(default_factory=dict)
    allowed_effect_kinds: list[str] = field(default_factory=list)
    allowed_reveals: list[str] = field(default_factory=list)
    forbidden: dict[str, Any] = field(default_factory=dict)
    # Auditor-only layer
    hidden_truths: list[dict[str, Any]] = field(default_factory=list)
    full_world_ref: str = ""


# ---------------------------------------------------------------------------
# TurnDraft — full lifecycle record of one turn
# ---------------------------------------------------------------------------

@dataclass
class TurnDraft:
    draft_id: str
    player_input: str = ""
    pre_world_ref: str = ""
    story_packet: StoryPacket | None = None
    writer_output: WriterOutput | None = None
    translated_claims: list[NarrativeClaim] = field(default_factory=list)
    deterministic_scan: dict[str, Any] = field(default_factory=dict)
    feasibility: FeasibilityReport | None = None
    writer_candidates: dict[str, WriterOutput] = field(default_factory=dict)
    candidate_audits: dict[str, dict[str, Any]] = field(default_factory=dict)
    winner_name: str = ""
    turn_wall_time_s: float = 0.0
    hard_audit: dict[str, Any] = field(default_factory=dict)
    soft_audit: dict[str, Any] = field(default_factory=dict)
    editor_tasks: list[RewriteTask] = field(default_factory=list)
    rewrite_history: list[dict[str, Any]] = field(default_factory=list)
    final_segments: list[Segment] = field(default_factory=list)
    candidate_patch: list[CandidatePatchEffect] = field(default_factory=list)
    admitted_patch: list[CandidatePatchEffect] = field(default_factory=list)
    post_world_ref: str = ""
    player_output: str = ""
    scorecard: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TurnDraft:
        # Basic reconstruction; caller may need deep conversion for nested objects
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
