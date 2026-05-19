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
    player_intent: dict[str, Any],
    seed: WorldSeed,
    grammar: NarrativeGrammar,
) -> NarrativeFrame:
    """Produce a NarrativeFrame for the current turn."""
    action = player_intent.get("action_type", "ambiguous")

    # 1. Select beat
    beat = _select_beat(action, grammar)

    # 2. Match hooks
    active_hooks = _match_hooks(action, player_intent, seed)

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

    # 5. Select motifs (max 2)
    motifs = _select_motifs(player_input, active_hooks, seed, grammar)

    # 6. Allowed commitment levels for this beat
    allowed_levels = _allowed_commitments_for_beat(beat, grammar)

    # 7. Forbidden moves
    forbidden = ["npc_inner_monologue"]
    if any(
        seed.active_hooks.get(hid, {}).get("hook_type") == "threshold"
        for hid in active_hooks
    ):
        forbidden.append("direct_hidden_truth_reveal")

    return NarrativeFrame(
        beat=beat,
        active_hooks=active_hooks,
        candidate_hints=list(dict.fromkeys(candidate_hints)),  # preserve order, dedupe
        motifs_to_use=motifs,
        dramatic_function=_dramatic_function(beat, active_hooks),
        allowed_commitment_levels=allowed_levels,
        forbidden_moves=forbidden,
    )


# ---------------------------------------------------------------------------
# Beat selection
# ---------------------------------------------------------------------------


_ACTION_TO_BEAT: dict[str, str] = {
    "inspect": "inspection",
    "ask": "social_pressure",
    "help": "social_pressure",
    "move": "threshold_crossing",
    "take": "inspection",
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


def _match_hooks(action: str, player_intent: dict[str, Any], seed: WorldSeed) -> list[str]:
    targets = [t.lower() for t in player_intent.get("targets", [])]
    props = [p.lower() for p in player_intent.get("props", [])]
    search_terms = set(targets + props)
    matched: list[str] = []

    for hook_id, hook in seed.active_hooks.items():
        subject = hook.get("subject", "").lower()
        hook_obj = hook.get("object", "").lower()

        # Direct subject/object match
        if subject in search_terms or hook_obj in search_terms:
            matched.append(hook_id)
            continue

        # Inspect action on items/locations
        if action == "inspect" and subject in search_terms:
            matched.append(hook_id)
            continue

        # NPC interaction matches lack/debt hooks
        if action in ("ask", "help") and hook.get("hook_type") in ("lack", "debt"):
            if subject in search_terms:
                matched.append(hook_id)
                continue

        # Move action: match threshold hooks by location fuzz
        if action == "move" and hook.get("hook_type") == "threshold":
            for term in search_terms:
                if _fuzzy_match(term, subject) or _fuzzy_match(term, hook_obj):
                    matched.append(hook_id)
                    break
            else:
                # Also check if term is a known location related to the hook
                for term in search_terms:
                    if _location_related_to_hook(term, hook, seed):
                        matched.append(hook_id)
                        break
            continue

    return matched


def _fuzzy_match(a: str, b: str) -> bool:
    """Simple overlap: one contains the other or they share a significant token."""
    a_lo = a.lower()
    b_lo = b.lower()
    if a_lo in b_lo or b_lo in a_lo:
        return True
    # token overlap for compound names like "lower_door" vs "lower_vault_door"
    a_tokens = set(a_lo.split("_"))
    b_tokens = set(b_lo.split("_"))
    return len(a_tokens & b_tokens) >= 1


def _location_related_to_hook(term: str, hook: dict[str, Any], seed: WorldSeed) -> bool:
    """Check if term is a location whose name overlaps with hook subject/object."""
    for loc_id in seed.locations:
        if _fuzzy_match(term, loc_id):
            subj = hook.get("subject", "")
            obj = hook.get("object", "")
            if _fuzzy_match(loc_id, subj) or _fuzzy_match(loc_id, obj):
                return True
    return False


# ---------------------------------------------------------------------------
# Motif selection
# ---------------------------------------------------------------------------


def _select_motifs(
    player_input: str,
    active_hooks: list[str],
    seed: WorldSeed,
    grammar: NarrativeGrammar,
) -> list[str]:
    pi_lower = player_input.lower()
    matched: list[str] = []

    # Match by label in player input
    for motif_id, motif in seed.motifs.items():
        label = motif.get("label", "").lower()
        if label in pi_lower:
            matched.append(motif_id)

    # Match by hook tension text
    for hook_id in active_hooks:
        hook = seed.active_hooks.get(hook_id, {})
        tension = hook.get("tension", "").lower()
        for motif_id, motif in seed.motifs.items():
            label = motif.get("label", "").lower()
            if label in tension and motif_id not in matched:
                matched.append(motif_id)

    max_motifs = grammar.motif_rules.get("max_motifs_per_turn", 2)
    return matched[:max_motifs]


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
