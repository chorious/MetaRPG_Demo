"""MotifScheduler — replaces label-substring motif selection.

Rules (v0.7.1):
1. Default 1 motif per turn.
2. Mechanical beat allows 0.
3. Force 1 if 3 turns without any motif.
4. Prefer motifs linked to active_hooks.
5. Cooldown ≥ 3 turns for same motif.
6. If repeating, pick a different variation.
7. Max 2 motifs per turn (grammar rule).

No direct WorldState mutation. Ledger is read-only input, schedule is output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from metarpg.agentic.narrative_grammar import NarrativeGrammar
from metarpg.agentic.seed_loader import WorldSeed


@dataclass
class MotifSchedule:
    motifs_to_use: list[str] = field(default_factory=list)
    required_variations: dict[str, str] = field(default_factory=dict)
    forbidden_repetition: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)  # v0.7.2: audit info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def schedule_motifs(
    beat: str,
    active_hooks: list[str],
    seed: WorldSeed,
    grammar: NarrativeGrammar,
    motif_ledger: dict[str, dict[str, Any]],
    current_turn: int = 0,
) -> MotifSchedule:
    """Schedule motifs for the current turn.

    Args:
        beat: Current beat type (e.g. "inspection", "threshold_crossing").
        active_hooks: List of active hook IDs.
        seed: WorldSeed with motif definitions.
        grammar: NarrativeGrammar with motif rules.
        motif_ledger: Dict of motif_id -> {last_used_turn, use_count, last_variation}.
        current_turn: Current turn number.
    """
    schedule = MotifSchedule()

    mechanical_beats = {"aftermath", "system", "meta"}
    allow_zero = beat in mechanical_beats

    max_motifs = grammar.motif_rules.get("max_motifs_per_turn", 2)
    if max_motifs < 1:
        return schedule

    # -- Phase 1: Score all available motifs --
    scored: list[tuple[str, float]] = []
    for motif_id, motif in seed.motifs.items():
        score = _score_motif(
            motif_id=motif_id,
            motif=motif,
            beat=beat,
            active_hooks=active_hooks,
            seed=seed,
            ledger=motif_ledger,
            current_turn=current_turn,
        )
        if score > 0:
            scored.append((motif_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # -- Phase 2: Determine how many motifs to select --
    turns_since_last = _turns_since_any_motif(motif_ledger, current_turn)
    force_one = turns_since_last >= 3

    if allow_zero and not force_one:
        schedule.debug = {
            "turns_since_last": turns_since_last,
            "force_one": False,
            "scored_count": len(scored),
            "allow_zero": True,
        }
        return schedule

    target_count = 1
    if force_one and not scored:
        # Force pick the least-recently-used motif even if score is 0
        scored = _all_motifs_by_recency(seed, motif_ledger)

    # -- Phase 3: Select motifs respecting constraints --
    selected: list[str] = []
    used_variations: dict[str, str] = {}
    skipped_cooldown: list[str] = []

    for motif_id, _score in scored:
        if len(selected) >= max_motifs:
            break

        # Cooldown check (v0.7.2: lowered from 3 to 2)
        entry = motif_ledger.get(motif_id, {})
        last_turn = entry.get("last_used_turn", -999)
        on_cooldown = current_turn - last_turn < 2 and last_turn >= 0
        if on_cooldown:
            # If force is active, bypass cooldown for the first available motif
            if force_one and not selected:
                pass  # allow this one through
            else:
                skipped_cooldown.append(motif_id)
                continue

        # Pick variation
        variation = _pick_variation(motif_id, seed, ledger=motif_ledger)

        selected.append(motif_id)
        if variation:
            used_variations[motif_id] = variation

    schedule.motifs_to_use = selected
    schedule.required_variations = used_variations

    # Forbidden repetitions = variations used in the last 2 turns
    schedule.forbidden_repetition = _gather_recent_variations(motif_ledger, current_turn, window=2)

    schedule.debug = {
        "turns_since_last": turns_since_last,
        "force_one": force_one,
        "scored_count": len(scored),
        "selected_count": len(selected),
        "skipped_cooldown": skipped_cooldown,
        "allow_zero": allow_zero,
    }

    return schedule


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_motif(
    motif_id: str,
    motif: dict[str, Any],
    beat: str,
    active_hooks: list[str],
    seed: WorldSeed,
    ledger: dict[str, dict[str, Any]],
    current_turn: int,
) -> float:
    """Score a motif for this turn. Higher = more suitable."""
    score = 0.0

    # Hook association bonus
    motif_functions = _parse_functions(motif.get("function", ""))
    for hook_id in active_hooks:
        hook = seed.active_hooks.get(hook_id, {})
        hook_type = hook.get("hook_type", "")
        if hook_type and hook_type in motif_functions:
            score += 3.0
        # Subject/object overlap bonus
        subject = hook.get("subject", "")
        obj = hook.get("object", "")
        if subject and any(subject in f for f in motif_functions):
            score += 1.5
        if obj and any(obj in f for f in motif_functions):
            score += 1.5

    # Beat-function alignment
    beat_alignment = {
        "inspection": {"clue", "contamination", "inspectable"},
        "threshold_crossing": {"threshold", "memory", "mechanism"},
        "social_pressure": {"lack", "debt", "trust"},
        "complication": {"danger", "time pressure", "depth"},
        "aftermath": {"echo", "memory", "time pressure"},
    }
    aligned = beat_alignment.get(beat, set())
    if motif_functions & aligned:
        score += 2.0

    # Recency penalty (favor motifs not used recently)
    entry = ledger.get(motif_id, {})
    last_turn = entry.get("last_used_turn", -999)
    if last_turn >= 0:
        turns_ago = current_turn - last_turn
        if turns_ago < 3:
            score -= 5.0  # strong penalty within cooldown
        elif turns_ago < 6:
            score -= 1.0
        elif turns_ago > 10:
            score += 1.0  # bonus for long absence

    # Underuse bonus (favor motifs used fewer times overall)
    use_count = entry.get("use_count", 0)
    if use_count == 0:
        score += 1.0
    elif use_count < 3:
        score += 0.5

    return score


def _parse_functions(function_text: str) -> set[str]:
    """Parse comma-separated function string into a set of normalized tokens."""
    return {f.strip().lower() for f in function_text.split(",") if f.strip()}


# ---------------------------------------------------------------------------
# Variation selection
# ---------------------------------------------------------------------------


def _pick_variation(
    motif_id: str,
    seed: WorldSeed,
    ledger: dict[str, dict[str, Any]],
) -> str | None:
    """Pick a variation for this motif, avoiding the most recent one if possible."""
    motif = seed.motifs.get(motif_id, {})
    variations = motif.get("allowed_variations", [])
    if not variations:
        return None

    entry = ledger.get(motif_id, {})
    last_var = entry.get("last_variation", "")

    # Try to avoid the last used variation
    candidates = [v for v in variations if v != last_var]
    if not candidates:
        candidates = variations

    # Simple round-robin: pick the one after last_var in the list
    if last_var and last_var in variations:
        idx = variations.index(last_var)
        next_idx = (idx + 1) % len(variations)
        return variations[next_idx]

    return candidates[0]


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------


def _turns_since_any_motif(ledger: dict[str, dict[str, Any]], current_turn: int) -> int:
    """How many turns since ANY motif was used.

    Returns 0 if no motif has ever been used (don't force on first turns).
    """
    last_turns = [
        entry.get("last_used_turn", -999)
        for entry in ledger.values()
    ]
    if not last_turns or all(t < 0 for t in last_turns):
        return 0  # never used → don't force
    most_recent = max(t for t in last_turns if t >= 0)
    return current_turn - most_recent


def _all_motifs_by_recency(
    seed: WorldSeed,
    ledger: dict[str, dict[str, Any]],
) -> list[tuple[str, float]]:
    """Return all motifs sorted by least recently used (fallback for force-one)."""
    scored: list[tuple[str, float]] = []
    for motif_id in seed.motifs:
        entry = ledger.get(motif_id, {})
        last_turn = entry.get("last_used_turn", -999)
        # Lower last_turn = higher score (older = more needed)
        score = -last_turn if last_turn >= 0 else 999
        scored.append((motif_id, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _gather_recent_variations(
    ledger: dict[str, dict[str, Any]], current_turn: int, window: int = 2
) -> list[str]:
    """Gather variations used in the last N turns (to forbid repetition)."""
    forbidden: list[str] = []
    for entry in ledger.values():
        last_turn = entry.get("last_used_turn", -999)
        if current_turn - last_turn <= window and last_turn >= 0:
            last_var = entry.get("last_variation", "")
            if last_var:
                forbidden.append(last_var)
    return forbidden


# ---------------------------------------------------------------------------
# Ledger update (called by runner at end of turn)
# ---------------------------------------------------------------------------


def update_motif_ledger(
    ledger: dict[str, dict[str, Any]],
    schedule: MotifSchedule,
    current_turn: int,
) -> dict[str, dict[str, Any]]:
    """Return an updated ledger after applying this turn's schedule.

    Non-mutating: returns a new dict (caller may assign back).
    """
    new_ledger = {k: dict(v) for k, v in ledger.items()}

    for motif_id in schedule.motifs_to_use:
        entry = new_ledger.setdefault(motif_id, {})
        entry["last_used_turn"] = current_turn
        entry["use_count"] = entry.get("use_count", 0) + 1
        if motif_id in schedule.required_variations:
            entry["last_variation"] = schedule.required_variations[motif_id]

    return new_ledger
