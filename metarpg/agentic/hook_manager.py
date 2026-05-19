"""Hook / Hint / Beat Manager — build NarrativeFrame from player intent and world seed.

Rules:
- Player action advances or surfaces hooks.
- Hints default to no-reveal of hidden truth.
- Motifs max 2 per turn, must vary if repeated.
- Beat serves the action without railroading.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.narrative_grammar import NarrativeGrammar
from metarpg.agentic.seed_loader import WorldSeed
from metarpg.agentic.transaction import NarrativeFrame


def build_narrative_frame(
    player_input: str,
    resolved_intent: Any,  # ResolvedIntent from reference_resolver
    seed: WorldSeed,
    grammar: NarrativeGrammar,
    world: Any | None = None,
    client=None,
) -> NarrativeFrame:
    """Produce a NarrativeFrame for the current turn.

    v0.7.1: consumes ResolvedIntent (canonical IDs), does NOT re-resolve.
    v0.7.2: optional L2 SemanticJudge for hook relevance when exact match fails.
    """
    # v0.7.1: accept either ResolvedIntent object or legacy dict
    if isinstance(resolved_intent, dict):
        action = resolved_intent.get("action_type", "ambiguous")
        raw_targets = [t.lower() for t in resolved_intent.get("targets", [])]
        raw_props = [p.lower() for p in resolved_intent.get("props", [])]
        resolved_targets = [_resolve_through_seed(t, seed) for t in raw_targets]
        resolved_props = [_resolve_through_seed(p, seed) for p in raw_props]
    else:
        action = resolved_intent.action_type if hasattr(resolved_intent, "action_type") else "ambiguous"
        resolved_targets = [
            r.canonical_id for r in (resolved_intent.targets if hasattr(resolved_intent, "targets") else [])
        ]
        resolved_props = [
            r.canonical_id for r in (resolved_intent.props if hasattr(resolved_intent, "props") else [])
        ]

    # 1. Select beat
    beat = _select_beat(action, grammar)

    # 2. Match hooks using canonical IDs from ResolvedIntent
    active_hooks, semantic_judgments = _match_hooks_v071(
        action, resolved_targets, resolved_props, seed, player_input, client
    )

    # 3. Surface dormant hooks
    for hook_id in active_hooks:
        hook = seed.active_hooks.get(hook_id, {})
        if hook.get("status") == "dormant":
            hook["status"] = "surfaced"

    # 4. Collect visible hints
    candidate_hints: list[str] = []
    for hook_id in active_hooks:
        hook = seed.active_hooks.get(hook_id, {})
        candidate_hints.extend(hook.get("visible_hints", []))

    # 5. Allowed commitment levels for this beat
    allowed_levels = _allowed_commitments_for_beat(beat, grammar)

    # 6. Forbidden moves
    forbidden = ["npc_inner_monologue"]
    if any(
        seed.active_hooks.get(hid, {}).get("hook_type") == "threshold"
        for hid in active_hooks
    ):
        forbidden.append("direct_hidden_truth_reveal")

    return NarrativeFrame(
        beat=beat,
        active_hooks=active_hooks,
        candidate_hints=list(dict.fromkeys(candidate_hints)),
        motifs_to_use=[],  # runner populates via schedule_motifs
        dramatic_function=_dramatic_function(beat, active_hooks),
        allowed_commitment_levels=allowed_levels,
        forbidden_moves=forbidden,
        resolved_targets=resolved_targets,
        resolved_props=resolved_props,
        unresolved_mentions=resolved_intent.unresolved if hasattr(resolved_intent, "unresolved") else [],
        semantic_judgments=semantic_judgments,
    )


# ---------------------------------------------------------------------------
# Beat selection
# ---------------------------------------------------------------------------


_ACTION_TO_BEAT: dict[str, str] = {
    "inspect": "inspection",
    "ask": "social_pressure",
    "speak": "social_pressure",
    "help": "social_pressure",
    "move": "threshold_crossing",
    "take": "inspection",
    "interact": "inspection",
    "give": "social_pressure",
    "wait": "aftermath",
    "attack": "complication",
}


def _select_beat(action: str, grammar: NarrativeGrammar) -> str:
    beat = _ACTION_TO_BEAT.get(action)
    if beat and beat in grammar.beat_types:
        return beat
    # fallback: find a beat whose default_hooks match active context
    return "arrival"


# ---------------------------------------------------------------------------
# Hook matching
# ---------------------------------------------------------------------------


def _resolve_through_seed(raw: str, seed: WorldSeed) -> str:
    """Try to resolve a raw mention to canonical ID via seed aliases."""
    if not raw:
        return raw
    # Direct hit on canonical ID
    if raw in seed.locations or raw in seed.entities or raw in seed.items:
        return raw
    # Try alias resolution (with underscore-to-space normalization)
    for variant in (raw, raw.replace("_", " ")):
        results = seed.resolve_alias(variant)
        if results:
            return results[0][0]  # canonical_id
    return raw


def _match_hooks_v071(
    action: str,
    resolved_targets: list[str],
    resolved_props: list[str],
    seed: WorldSeed,
    player_input: str = "",
    client=None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Match hooks using canonical IDs from ResolvedIntent (v0.7.2).

    Fast path: exact subject/object match by canonical ID.
    Slow path (v0.7.2): L2 SemanticJudge for hooks that fail exact match.
    """
    search_ids = set(resolved_targets + resolved_props)
    matched: list[str] = []
    unmatched_hooks: list[dict[str, Any]] = []

    for hook_id, hook in seed.active_hooks.items():
        subject = hook.get("subject", "")
        hook_obj = hook.get("object", "")
        hook_type = hook.get("hook_type", "")

        # Direct subject/object match by canonical ID
        if subject in search_ids or hook_obj in search_ids:
            matched.append(hook_id)
            continue

        # Inspect action on items/locations
        if action in ("inspect", "move") and subject in search_ids:
            matched.append(hook_id)
            continue

        # NPC interaction matches lack/debt hooks
        if action in ("ask", "help", "speak") and hook_type in ("lack", "debt"):
            if subject in search_ids:
                matched.append(hook_id)
                continue

        # Move action: match threshold hooks by location
        if action == "move" and hook_type == "threshold":
            if subject in search_ids or hook_obj in search_ids:
                matched.append(hook_id)
                continue

        # v0.7.2: collect unmatched hooks for L2 semantic judge
        unmatched_hooks.append({"id": hook_id, **hook})

    semantic_judgments: list[dict[str, Any]] = []

    # L2 fallback: semantic judge for unmatched hooks
    if unmatched_hooks and client is not None and matched:
        try:
            from metarpg.agentic import semantic_judge
            player_intent = {
                "action_type": action,
                "targets": resolved_targets,
                "props": resolved_props,
                "player_input": player_input,
            }
            recent_events = []
            if hasattr(seed, "_recent_events"):
                recent_events = seed._recent_events
            judgments = semantic_judge.judge_hook_relevance(
                player_intent=player_intent,
                active_hooks=unmatched_hooks,
                recent_events=recent_events,
                client=client,
            )
            for j in judgments:
                real_hook_id = j.hook_id or j.category
                # v0.7.2.1: whitelist guard — only canonical seed hook ids allowed
                if real_hook_id not in seed.active_hooks:
                    semantic_judgments.append({
                        "hook_id": None,
                        "category": j.category,
                        "verdict": "ignored",
                        "evidence": f"Non-canonical hook_id '{real_hook_id}' ignored",
                        "confidence": j.confidence,
                    })
                    continue
                semantic_judgments.append({
                    "hook_id": real_hook_id,
                    "category": j.category,
                    "verdict": j.verdict,
                    "evidence": j.evidence,
                    "confidence": j.confidence,
                })
                if j.verdict == "pass":
                    matched.append(real_hook_id)
        except Exception:
            # L2 failure is non-blocking; exact-match results are preserved
            pass

    # v0.7.2.1: defensive guard — active_hooks can only contain canonical ids
    canonical_ids = set(seed.active_hooks.keys())
    matched = [h for h in matched if h in canonical_ids]

    return matched, semantic_judgments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allowed_commitments_for_beat(beat: str, grammar: NarrativeGrammar) -> list[str]:
    beat_info = grammar.beat_types.get(beat, {})
    default_hooks = beat_info.get("default_hooks", [])
    # event and utterance are universal; every turn is an event and may contain speech.
    levels: set[str] = {"event", "utterance"}
    for ht in default_hooks:
        hook_type_info = grammar.hook_types.get(ht, {})
        levels.update(hook_type_info.get("allowed_commitments", []))
    return sorted(levels)


def _dramatic_function(beat: str, active_hooks: list[str]) -> str:
    if active_hooks:
        return f"{beat} driven by {', '.join(active_hooks)}"
    return beat
