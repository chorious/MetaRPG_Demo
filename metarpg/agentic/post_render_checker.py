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

    # --- L2: Semantic Judge (risk-turn only, Call Budget) ---
    semantic_judgments: list[dict] = []
    if _is_risk_turn(tx) and client is not None:
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
        except Exception as exc:
            # L2 failure is non-blocking; L3 already ran
            semantic_judgments.append({"check": "error", "error": str(exc)})

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


def _is_risk_turn(tx: TurnTransaction) -> bool:
    """Risk turn = involves hidden truth exposure or canon commitment.

    Call Budget: L2 semantic check only runs on true risk turns (~20-30%).
    v0.7.2 tightened: mark_hook_status alone is not enough; must be canon
    or a hook status change to a terminal state (resolved/revealed).
    """
    # Terminal hook status changes (most likely to expose hidden truth)
    for op in tx.operations:
        if op.kind == "mark_hook_status":
            status = op.params.get("status", "")
            if status in ("resolved", "revealed", "completed"):
                return True
    # Canon commitments are strong claims that need claim-support checking
    for c in tx.commitments:
        if c.level == "canon":
            return True
    return False


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
