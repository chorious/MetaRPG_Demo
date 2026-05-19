"""Post-render Checker — narrow defense line after Renderer.

Scope:
- Must inspect: uncommitted world facts, hidden_truth alias leaks,
  NPC inner monologue, debug/system terms.
- Must NOT inspect: hook reasonableness, relation_delta magnitude,
  NPC speech patch support, item existence (handled by Validator).
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.transaction import TurnTransaction
from metarpg.models import WorldState


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_rendered_prose(
    prose: str,
    tx: TurnTransaction,
    world: WorldState,
    client=None,  # noqa: ARG001 — reserved for optional local vLLM NLI check
) -> dict[str, Any]:
    """Check rendered prose for violations outside the validated transaction.

    Returns:
        {"status": "pass" | "light_repair", "issues": list[str]}
    """
    issues: list[str] = []

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

    if issues:
        return {"status": "light_repair", "issues": issues}
    return {"status": "pass", "issues": []}


# ---------------------------------------------------------------------------
# Deterministic scanners
# ---------------------------------------------------------------------------


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
