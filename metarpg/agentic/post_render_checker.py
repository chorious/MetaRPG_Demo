"""Post-render Checker — narrow defense line after Renderer.

Scope:
- Must inspect: uncommitted world facts, hidden_truth alias leaks,
  NPC inner monologue, debug/system terms.
- Must NOT inspect: hook reasonableness, relation_delta magnitude,
  NPC speech patch support, item existence (handled by Validator).

v0.7.1:
- L3 keyword scan always runs (fast, deterministic).
- L2 SemanticJudge runs only on risk turns (hidden truth / hook change / canon).
- Call budget: L2 skipped if client unavailable; never blocks pipeline.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.transaction import TurnTransaction
from metarpg.models import WorldState

# v0.7.1: optional L2 semantic judge (lazy import to avoid circular deps)
_judge_mod = None


def _get_semantic_judge():
    global _judge_mod
    if _judge_mod is None:
        from metarpg.agentic import semantic_judge as _judge_mod
    return _judge_mod


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_rendered_prose(
    prose: str,
    tx: TurnTransaction,
    world: WorldState,
    client=None,
) -> dict[str, Any]:
    """Check rendered prose for violations outside the validated transaction.

    Returns:
        {"status": "pass" | "repaired" | "failed", "issues": list[str]}

    Status semantics (v0.7.2.1):
        pass    = L3 clean + L2 pass
        repaired = issues found but not critical (L3 hits or L2 downgrade)
        failed  = L2 reject or hidden-truth non-pass (critical)
    """
    issues: list[str] = []

    # --- L3: Deterministic keyword scan (always runs) ---
    # 1. Hidden truth alias leaks
    for alias in _collect_hidden_aliases(world):
        if alias.lower() in prose.lower():
            issues.append(f"Hidden truth alias leak: {alias!r}")

    # 2. NPC inner monologue
    if _contains_npc_inner_monologue(prose):
        issues.append("NPC inner monologue detected")

    # 3. Debug / system terms
    if _contains_debug_terms(prose):
        issues.append("Debug or system terminology detected")

    # 4. Uncommitted world facts (deterministic heuristic)
    uncommitted = _find_uncommitted_facts(prose, tx, world)
    for fact in uncommitted:
        issues.append(f"Uncommitted world fact: {fact!r}")

    # --- L2: Semantic Judge (required-turn must run, fail-closed v0.7.5) ---
    semantic_judgments: list[dict] = []
    l2_required = _is_l2_required(tx)

    if l2_required:
        if client is None:
            issues.append("L2 required but semantic judge client unavailable")
            return {"status": "failed", "issues": issues, "semantic_judgments": []}

        try:
            judge = _get_semantic_judge()
            # Hidden truth exposure check
            hidden_truths = [
                {"id": k, "statement": v.get("statement", "")}
                for k, v in getattr(world, "hidden_truths", {}).items()
                if isinstance(v, dict)
            ]
            ht_judgment = judge.judge_hidden_truth_exposure(
                text=prose,
                hidden_truths=hidden_truths,
                client=client,
            )
            semantic_judgments.append({
                "check": "hidden_truth_exposure",
                "verdict": ht_judgment.verdict,
                "category": ht_judgment.category,
                "evidence": ht_judgment.evidence,
            })
            if ht_judgment.verdict in ("downgrade", "reject"):
                issues.append(
                    f"L2 semantic: hidden truth exposure ({ht_judgment.category}): "
                    f"{ht_judgment.evidence}"
                )

            # Render claim support check
            tx_summary = {
                "operations": [op.kind for op in tx.operations],
                "commitments": [c.level for c in tx.commitments],
            }
            world_facts = [str(f) for f in getattr(world, "facts", [])]
            rc_judgment = judge.judge_render_claim_support(
                prose=prose,
                transaction_summary=tx_summary,
                world_facts=world_facts,
                client=client,
            )
            semantic_judgments.append({
                "check": "render_claim_support",
                "verdict": rc_judgment.verdict,
                "category": rc_judgment.category,
                "evidence": rc_judgment.evidence,
            })
            if rc_judgment.verdict == "reject":
                issues.append(
                    f"L2 semantic: unsupported claim ({rc_judgment.category}): "
                    f"{rc_judgment.evidence}"
                )

            # v0.7.4: Intent Fulfillment check
            if_judgment = judge.judge_intent_fulfillment(
                player_input=tx.player_input or "",
                resolved_intent=tx.player_intent or {},
                prose=prose,
                transaction_summary=tx_summary,
                current_turn_obligation=tx.render_brief.current_turn_obligation or None,
                client=client,
            )
            semantic_judgments.append({
                "check": "intent_fulfillment",
                "verdict": if_judgment.verdict,
                "category": if_judgment.category,
                "evidence": if_judgment.evidence,
            })
            if if_judgment.verdict == "reject":
                issues.append(
                    f"L2 semantic: intent fulfillment ({if_judgment.category}): "
                    f"{if_judgment.evidence}"
                )

            # v0.7.5: Object personification check
            visible_objects = tx.render_brief.visible_objects or []
            if visible_objects:
                op_judgment = judge.judge_object_personification(
                    prose=prose,
                    visible_objects=visible_objects,
                    client=client,
                )
                semantic_judgments.append({
                    "check": "object_personification",
                    "verdict": op_judgment.verdict,
                    "category": op_judgment.category,
                    "evidence": op_judgment.evidence,
                })
                if op_judgment.verdict == "reject":
                    issues.append(
                        f"L2 semantic: object personification ({op_judgment.category}): "
                        f"{op_judgment.evidence}"
                    )
        except Exception as exc:
            # v0.7.5: L2 required but failed = fail-closed
            issues.append(f"L2 required but semantic judge failed: {exc}")
            return {
                "status": "failed",
                "issues": issues,
                "semantic_judgments": semantic_judgments + [{"check": "error", "error": str(exc)}],
            }

    if not issues:
        return {"status": "pass", "issues": [], "semantic_judgments": semantic_judgments}

    # v0.7.4: classify as failed if any critical L2 issue
    has_l2_reject = any(
        "L2 semantic: unsupported claim" in iss or
        "L2 semantic: intent fulfillment" in iss or
        ("L2 semantic: hidden truth exposure" in iss and "reject" in iss)
        for iss in issues
    )
    # hidden truth downgrade is also non-pass
    has_hidden_nonpass = any(
        "L2 semantic: hidden truth exposure" in iss
        for iss in issues
    )
    if has_l2_reject or has_hidden_nonpass:
        return {"status": "failed", "issues": issues, "semantic_judgments": semantic_judgments}
    return {"status": "repaired", "issues": issues, "semantic_judgments": semantic_judgments}


# ---------------------------------------------------------------------------
# Deterministic scanners
# ---------------------------------------------------------------------------


def _is_l2_required(tx: TurnTransaction) -> bool:
    """Determine if L2 semantic judge MUST run for this turn (v0.7.5).

    A turn is L2-required if any of the following hold:
    - Terminal hook status changes (resolved/revealed/completed)
    - Canon commitments
    - Forbidden claims
    - Obligation-bearing response modes (unreachable/absence/fallback/safe_fallback)
    - must_not_claim is non-empty
    - Operations include speak or observe_reaction
    - Resolved target is unavailable (available=false)
    - Candidate hints hit hidden_truth symbolic risk
    """
    # 1. Terminal hook status changes
    for op in tx.operations:
        if op.kind == "mark_hook_status":
            status = op.params.get("status", "")
            if status in ("resolved", "revealed", "completed"):
                return True

    # 2. Canon commitments
    for c in tx.commitments:
        if c.level == "canon":
            return True

    # 3. Forbidden claims
    if tx.forbidden_claims:
        return True

    # 4. Obligation-bearing response modes (from render_brief)
    obligation = tx.render_brief.current_turn_obligation or {}
    response_mode = obligation.get("response_mode", "")
    if response_mode in ("unreachable", "absence", "fallback", "safe_fallback"):
        return True

    # 5. must_not_claim non-empty
    if obligation.get("must_not_claim", []):
        return True

    # 6. speak / observe_reaction operations
    for op in tx.operations:
        if op.kind in ("speak", "observe_reaction"):
            return True

    # 7. Resolved target available=false
    for target in tx.player_intent.get("targets", []):
        if isinstance(target, dict) and target.get("available") is False:
            return True

    # 8. Candidate hints hit hidden_truth symbolic risk
    symbolic_risk_patterns = ("code", "number", "password", "secret", "hidden", "truth")
    for hint in tx.narrative_frame.candidate_hints:
        hint_lower = hint.lower()
        if any(p in hint_lower for p in symbolic_risk_patterns):
            return True

    # 9. Backward compat: assumption source (unreachable/absence/fallback)
    for assumption in tx.assumptions:
        source = assumption.get("source", "")
        if source in ("unreachable_location_response", "absence_response", "fallback"):
            return True

    return False


def _is_risk_turn(tx: TurnTransaction) -> bool:
    """Deprecated: use _is_l2_required. Kept for backward compat."""
    return _is_l2_required(tx)


def _collect_hidden_aliases(world: WorldState) -> list[str]:
    aliases: list[str] = []
    hidden_truths = getattr(world, "hidden_truths", {})
    if not isinstance(hidden_truths, dict):
        return aliases
    for ht in hidden_truths.values():
        if isinstance(ht, dict):
            aliases.extend(ht.get("aliases", []))
        elif hasattr(ht, "aliases"):
            a = ht.aliases
            aliases.extend(list(a) if not isinstance(a, str) else [a])
    return aliases


_NPC_INNER_INDICATORS: set[str] = {
    "心想",
    "内心",
    "在心里",
    "暗自",
    "默念",
    "心底",
    "思索着",
    "想着",
}


def _contains_npc_inner_monologue(prose: str) -> bool:
    # Heuristic: Chinese phrases that indicate internal thought.
    # A full solution would require coreference resolution (v0.7.1+).
    return any(ind in prose for ind in _NPC_INNER_INDICATORS)


_DEBUG_TERMS: set[str] = {
    "DEBUG",
    "SYSTEM",
    "TRANSACTION",
    "HOOK_ID",
    "CANON_FACT",
    "NPC_INNER",
    "fallback",
    "schema",
    "validation",
}


def _contains_debug_terms(prose: str) -> bool:
    return any(term in prose for term in _DEBUG_TERMS)


def _find_uncommitted_facts(
    prose: str, tx: TurnTransaction, world: WorldState
) -> list[str]:
    """Heuristic: flag mentions of locations/items/entities not present in tx or world.

    MVP implementation: only flag obviously new locations (not in world.locations)
    and items (not derivable from world.facts). Full NLI check deferred to v0.7.1.
    """
    violations: list[str] = []
    prose_lower = prose.lower()

    # Check for location mentions not in world
    # (very conservative: we only know world.locations; prose may refer to them
    #  with different wording, so false positives are acceptable for MVP)
    known_locations = {loc.lower() for loc in world.locations}
    # This is intentionally a placeholder; a real implementation needs
    # entity linking or NLI. For MVP we keep it empty to avoid over-flagging.
    return violations
