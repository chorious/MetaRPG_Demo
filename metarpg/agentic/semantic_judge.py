"""SemanticJudge — L2: narrative semantic boundary checks via local vLLM.

MVP (v0.7.1): 3 functions only.
- judge_hook_relevance
- judge_hidden_truth_exposure
- judge_render_claim_support

All outputs are structured SemanticJudgment dataclasses.
No function in this module may mutate WorldState.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from metarpg.agentic.model_client import LlmClient


@dataclass
class SemanticJudgment:
    verdict: Literal["pass", "downgrade", "reject"]
    category: str
    evidence: str
    suggested_downgrade: str | None
    confidence: float
    hook_id: str | None = None  # v0.7.2.1: only populated by judge_hook_relevance


# ---------------------------------------------------------------------------
# 1. judge_hook_relevance
# ---------------------------------------------------------------------------


def judge_hook_relevance(
    player_intent: dict[str, Any],
    active_hooks: list[dict[str, Any]],
    recent_events: list[str],
    client: LlmClient | None = None,
) -> list[SemanticJudgment]:
    """Judge which active hooks are semantically relevant to the current intent.

    Returns a list of judgments, one per hook assessed.
    If client is None, returns empty list (no judgment).
    """
    if client is None or not active_hooks:
        return []

    system_prompt = (
        "You are a narrative semantics judge for an RPG engine.\n"
        "Given the player's intent and a list of active narrative hooks, "
        "judge whether each hook is relevant to this turn.\n"
        "Output JSON only, no markdown fences.\n\n"
        "Verdict rules:\n"
        '- "pass" = the hook is strongly relevant to the player intent or recent events\n'
        '- "downgrade" = weak relevance; the hook should not advance status this turn\n'
        '- "reject" = no relevance; do not mention this hook\n\n'
        "Output format:\n"
        '{"judgments": [{"hook_id": "...", "verdict": "pass|downgrade|reject", '
        '"category": "...", "evidence": "...", "suggested_downgrade": "...", '
        '"confidence": 0.0-1.0}]}'
    )

    user_prompt = json.dumps(
        {
            "player_intent": player_intent,
            "active_hooks": [
                {"hook_id": h.get("id", ""), "tension": h.get("tension", "")}
                for h in active_hooks
            ],
            "recent_events": recent_events[-5:] if recent_events else [],
        },
        ensure_ascii=False,
        indent=2,
    )

    return _call_judge(system_prompt, user_prompt, client)


# ---------------------------------------------------------------------------
# 2. judge_hidden_truth_exposure
# ---------------------------------------------------------------------------


def judge_hidden_truth_exposure(
    text: str,
    hidden_truths: list[dict[str, Any]],
    reveal_policy: str = "hint_first",
    client: LlmClient | None = None,
) -> SemanticJudgment:
    """Judge whether a piece of text (prose or operation) exposes hidden truths.

    Returns a single judgment.
    If client is None, returns a permissive 'pass' judgment.
    """
    if client is None:
        return SemanticJudgment(
            verdict="pass",
            category="no_llm_available",
            evidence="SemanticJudge skipped: no client provided",
            suggested_downgrade=None,
            confidence=0.0,
        )

    system_prompt = (
        "You are a narrative semantics judge for an RPG engine.\n"
        "Given a piece of text and hidden truths that must NOT be directly revealed, "
        "judge the exposure level.\n"
        "Output JSON only, no markdown fences.\n\n"
        "Exposure levels:\n"
        '- "pass" = no hidden truth is exposed; safe\n'
        '- "downgrade" = a weak hint or atmospheric allusion; acceptable but monitor\n'
        '- "reject" = strong hint or direct reveal; must be blocked\n\n'
        "Output format:\n"
        '{"verdict": "pass|downgrade|reject", "category": "...", '
        '"evidence": "...", "suggested_downgrade": "...", "confidence": 0.0-1.0}'
    )

    # v0.7.3: include symbolic_risk_patterns and safe_hint_boundary
    ht_payload = []
    for t in hidden_truths:
        entry = {
            "id": t.get("id", ""),
            "statement": t.get("statement", ""),
        }
        if "symbolic_risk_patterns" in t:
            entry["symbolic_risk_patterns"] = t["symbolic_risk_patterns"]
        if "safe_hint_boundary" in t:
            entry["safe_hint_boundary"] = t["safe_hint_boundary"]
        ht_payload.append(entry)

    user_prompt = json.dumps(
        {
            "text": text,
            "hidden_truths": ht_payload,
            "reveal_policy": reveal_policy,
            "instructions": (
                "Do not flag text that only mentions numbers or objects in isolation. "
                "Only flag when a specific combination (number + object + action/response context) "
                "creates a bridge to the hidden truth. Use safe_hint_boundary.allowed as guidance."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )

    results = _call_judge(system_prompt, user_prompt, client)
    return results[0] if results else SemanticJudgment(
        verdict="pass",
        category="parse_error",
        evidence="Judge returned no results",
        suggested_downgrade=None,
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# 3. judge_render_claim_support
# ---------------------------------------------------------------------------


def judge_render_claim_support(
    prose: str,
    transaction_summary: dict[str, Any],
    world_facts: list[str],
    client: LlmClient | None = None,
) -> SemanticJudgment:
    """Judge whether rendered prose contains claims unsupported by committed facts.

    Returns a single judgment.
    If client is None, returns a permissive 'pass' judgment.
    """
    if client is None:
        return SemanticJudgment(
            verdict="pass",
            category="no_llm_available",
            evidence="SemanticJudge skipped: no client provided",
            suggested_downgrade=None,
            confidence=0.0,
        )

    system_prompt = (
        "You are a narrative semantics judge for an RPG engine.\n"
        "Given rendered prose and the committed world facts, "
        "judge whether the prose introduces unsupported claims.\n"
        "Output JSON only, no markdown fences.\n\n"
        "Verdict rules:\n"
        '- "pass" = all claims in prose are supported by committed facts or harmless texture\n'
        '- "downgrade" = prose contains plausible but unverified texture; acceptable\n'
        '- "reject" = prose asserts new facts not in committed transaction or world state\n\n'
        "Output format:\n"
        '{"verdict": "pass|downgrade|reject", "category": "...", '
        '"evidence": "...", "suggested_downgrade": "...", "confidence": 0.0-1.0}'
    )

    user_prompt = json.dumps(
        {
            "prose": prose,
            "transaction_summary": transaction_summary,
            "world_facts": world_facts[-20:] if len(world_facts) > 20 else world_facts,
        },
        ensure_ascii=False,
        indent=2,
    )

    results = _call_judge(system_prompt, user_prompt, client)
    return results[0] if results else SemanticJudgment(
        verdict="pass",
        category="parse_error",
        evidence="Judge returned no results",
        suggested_downgrade=None,
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# 4. judge_intent_fulfillment (v0.7.4)
# ---------------------------------------------------------------------------


def judge_intent_fulfillment(
    player_input: str,
    resolved_intent: dict[str, Any],
    prose: str,
    transaction_summary: dict[str, Any],
    client: LlmClient | None = None,
) -> SemanticJudgment:
    """Judge whether rendered prose fulfills the current turn's player intent.

    Returns a single judgment.
    If client is None, returns a permissive 'pass' judgment.
    """
    if client is None:
        return SemanticJudgment(
            verdict="pass",
            category="no_llm_available",
            evidence="SemanticJudge skipped: no client provided",
            suggested_downgrade=None,
            confidence=0.0,
        )

    system_prompt = (
        "You are a narrative semantics judge for an RPG engine.\n"
        "Given the player's input, their resolved intent, and the rendered prose, "
        "judge whether the prose actually responds to what the player tried to do THIS turn.\n"
        "Output JSON only, no markdown fences.\n\n"
        "Verdict rules:\n"
        '- "pass" = prose clearly responds to the current turn\'s player action/target\n'
        '- "downgrade" = prose responds to the general direction but mixes in stale context or wrong emphasis\n'
        '- "reject" = prose narrates a different action, different target, or old turn events; '
        'or treats an unreachable/absent target as if it were present and interacted with\n\n'
        "Categories:\n"
        '- "intent_fulfilled" = prose matches player_input and resolved_intent\n'
        '- "wrong_action" = prose describes a different action than player_input\n'
        '- "wrong_target" = prose focuses on a different target than resolved_intent\n'
        '- "stale_context" = prose repeats or continues a previous turn\'s narrative instead of the current one\n'
        '- "unsupported_continuation" = prose claims an action succeeded that the transaction did not commit\n'
        '- "missing_refusal" = prose should acknowledge an absent/unreachable target but does not\n'
        '- "over_answered" = prose invents outcomes or details not in the transaction\n\n'
        "Output format:\n"
        '{"verdict": "pass|downgrade|reject", "category": "...", '
        '"evidence": "...", "suggested_downgrade": "...", "confidence": 0.0-1.0}'
    )

    user_prompt = json.dumps(
        {
            "player_input": player_input,
            "resolved_intent": resolved_intent,
            "prose": prose,
            "transaction_summary": transaction_summary,
            "instructions": (
                "Do not penalize prose for omitting historical context. "
                "Do penalize prose that narrates a different action or a different target than the current intent. "
                "If the transaction was a fallback/absence/unreachable response, the prose should be short and grounded, "
                "not a detailed narrative of a different action."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )

    results = _call_judge(system_prompt, user_prompt, client)
    return results[0] if results else SemanticJudgment(
        verdict="pass",
        category="parse_error",
        evidence="Judge returned no results",
        suggested_downgrade=None,
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# Shared LLM call helper
# ---------------------------------------------------------------------------


def _call_judge(
    system_prompt: str, user_prompt: str, client: LlmClient
) -> list[SemanticJudgment]:
    """Call local vLLM and parse structured judgment output."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = client.chat_json(messages, temperature=0.2)
    except Exception:
        return []

    # Normalize: may be a single judgment object or {"judgments": [...]}
    judgments_data: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        if "judgments" in raw and isinstance(raw["judgments"], list):
            judgments_data = raw["judgments"]
        else:
            judgments_data = [raw]
    elif isinstance(raw, list):
        judgments_data = raw

    results: list[SemanticJudgment] = []
    for j in judgments_data:
        if not isinstance(j, dict):
            continue
        verdict = j.get("verdict", "pass")
        if verdict not in ("pass", "downgrade", "reject"):
            verdict = "pass"
        results.append(
            SemanticJudgment(
                verdict=verdict,
                category=j.get("category", ""),
                evidence=j.get("evidence", ""),
                suggested_downgrade=j.get("suggested_downgrade"),
                confidence=float(j.get("confidence", 0.5)),
                hook_id=j.get("hook_id"),
            )
        )

    return results
