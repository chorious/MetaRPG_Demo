"""Dynamic action contract — v0.4.

STORY2GAME-inspired explicit precondition/effect schema.

Heuristic and future-LLM proposers should emit hypotheses whose claims and
effects map cleanly to this contract. The engine validates; it does not execute
generated code.

Mapping:
  STORY2GAME preconditions  -> support_claims (Claim)
  STORY2GAME effects        -> proposed_effects (ProposedEffect)
  Dynamic action generation -> open MetaAct hypothesis proposal
  State representation update -> schema/claim/object materialization admission
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClaimContract:
    """A claim / precondition in the action contract."""

    name: str
    args: list[str]
    expected_status: str = ""  # "accepted", "inferred", "probable" — hint only


@dataclass
class EffectContract:
    """An effect / postcondition in the action contract."""

    kind: str
    args: list[Any]
    impact: int = 0  # 0=flavor, 1=social, 2=belief, 3=hard fact


@dataclass
class SubActContract:
    """One sub-action with explicit claims and effects."""

    kind: str
    actor: str
    args: list[str] = field(default_factory=list)
    claims: list[ClaimContract] = field(default_factory=list)
    effects: list[EffectContract] = field(default_factory=list)
    impact: int = 0


@dataclass
class ActionContract:
    """Top-level contract for a dynamic action hypothesis."""

    act_kind: str
    confidence: float
    subacts: list[SubActContract] = field(default_factory=list)
    raw_text: str = ""
    target: str = ""
    topic: str = ""
    source: str = ""      # e.g. "llm", "heuristic", "template"


# ---------- validation ----------


def validate_contract(contract: ActionContract) -> list[str]:
    """Check a contract for obvious structural errors.

    Returns a list of human-readable error messages.
    """
    errors: list[str] = []
    if not contract.act_kind:
        errors.append("missing act_kind")
    if contract.confidence < 0 or contract.confidence > 1:
        errors.append(f"confidence out of range: {contract.confidence}")

    for i, sub in enumerate(contract.subacts):
        if not sub.kind:
            errors.append(f"subact[{i}]: missing kind")
        if not sub.claims:
            errors.append(f"subact[{i}]: no claims (effects would be ungrounded)")
        for j, eff in enumerate(sub.effects):
            if eff.impact < 0 or eff.impact > 4:
                errors.append(f"subact[{i}] effect[{j}]: invalid impact {eff.impact}")
            if eff.kind not in _KNOWN_EFFECT_KINDS:
                errors.append(f"subact[{i}] effect[{j}]: unknown kind '{eff.kind}'")

    return errors


# Supported effect kinds for contract validation
_KNOWN_EFFECT_KINDS: set[str] = {
    "event", "transient_event", "canon_event", "observe", "dialogue",
    "travel", "add_fact", "remove_fact", "add_knowledge",
    "add_object", "remove_object", "relationship_change",
    "rel_delta", "belief_delta", "motif_delta",
    "attention_delta", "risk_flag", "flag_set",
    "consume_hook", "decay_hook", "promote_hook", "hook_create",
    "motif_activate", "motif_resolve",
    "plot_thread_open", "plot_thread_advance", "plot_thread_close",
}


# ---------- conversion helpers ----------


def contract_to_hypothesis(contract: ActionContract) -> "ActHypothesis | None":
    """Convert an ActionContract to the internal ActHypothesis shape.

    Returns None if validation errors exist.
    """
    from .models import ActHypothesis, Claim, ClaimStatus, ProposedEffect, SubAct

    errors = validate_contract(contract)
    if errors:
        return None

    subacts: list[SubAct] = []
    for sc in contract.subacts:
        claims = [
            Claim(c.name, tuple(c.args), ClaimStatus.UNKNOWN, "")
            for c in sc.claims
        ]
        effects = [
            ProposedEffect(e.kind, tuple(e.args), e.impact)
            for e in sc.effects
        ]
        subacts.append(SubAct(
            kind=sc.kind,
            actor=sc.actor,
            args=tuple(sc.args),
            claims=claims,
            effects=effects,
            impact=sc.impact,
        ))

    return ActHypothesis(
        act_kind=contract.act_kind,
        confidence=contract.confidence,
        subacts=subacts,
        raw_text=contract.raw_text,
        target=contract.target,
        topic=contract.topic,
    )
