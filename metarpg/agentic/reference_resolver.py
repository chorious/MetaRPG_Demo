"""ReferenceResolver — L1: natural language mention → canonical ID.

Rules (per v0.7.1 plan):
1. Exact alias phrase match first (confidence 0.95).
2. Containment match second (confidence 0.85).
3. LLM fallback for unresolved mentions.
4. Ambiguous results with confidence < 0.7 → mark as unresolved.

Call discipline: runner calls this ONCE per turn. All downstream stages
consume the resulting ResolvedIntent — no duplicate resolution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from metarpg.agentic.model_client import LlmClient


@dataclass
class ResolvedRef:
    mention: str
    canonical_id: str
    kind: str  # entity | item | location | hook | motif
    confidence: float
    available: bool = True  # v0.7.2: is this ref currently visible/reachable/present?


@dataclass
class ResolvedIntent:
    action_type: str = ""
    targets: list[ResolvedRef] = field(default_factory=list)
    props: list[ResolvedRef] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_references(
    player_input: str,
    known_entities: list[str],
    known_items: list[str],
    known_locations: list[str],
    known_hooks: list[str],
    known_motifs: list[str],
    aliases_map: dict[str, list[str]],  # canonical_id -> list of alias phrases
    available_entities: list[str] | None = None,
    available_items: list[str] | None = None,
    available_locations: list[str] | None = None,
    available_hooks: list[str] | None = None,
    available_motifs: list[str] | None = None,
    client: LlmClient | None = None,
    last_targets: list[ResolvedRef] | None = None,
    player_location: str = "",
) -> ResolvedIntent:
    """Resolve player input mentions to canonical IDs.

    Resolution order:
    1. Deterministic alias matching against known_universe (exact + containment).
    2. Contextual coreference for pronouns / omitted subjects / "that door"
       (only if alias match produced no targets).
    3. LLM fallback for unresolved mentions (only if client provided).

    v0.7.2: Each ResolvedRef carries an `available` flag.
    """
    if not player_input or not player_input.strip():
        return ResolvedIntent(action_type="none")

    # Build availability sets (default to known = available for backward compat)
    avail_entities = set(available_entities) if available_entities is not None else set(known_entities)
    avail_items = set(available_items) if available_items is not None else set(known_items)
    avail_locations = set(available_locations) if available_locations is not None else set(known_locations)
    avail_hooks = set(available_hooks) if available_hooks is not None else set(known_hooks)
    avail_motifs = set(available_motifs) if available_motifs is not None else set(known_motifs)

    # Phase 1: deterministic alias matching
    intent = _resolve_aliases_deterministic(
        player_input,
        known_entities,
        known_items,
        known_locations,
        known_hooks,
        known_motifs,
        aliases_map,
        avail_entities,
        avail_items,
        avail_locations,
        avail_hooks,
        avail_motifs,
    )

    # Phase 1.5: contextual coreference (only when alias match failed to find targets)
    if not intent.targets and last_targets:
        coref_refs = _resolve_coreference(
            player_input, last_targets, player_location,
            known_entities, known_items, known_locations, known_hooks, known_motifs, aliases_map,
            avail_entities, avail_items, avail_locations, avail_hooks, avail_motifs,
        )
        intent.targets.extend(coref_refs)
        if coref_refs and intent.unresolved:
            intent.unresolved = []

    # Phase 2: LLM fallback for unresolved mentions
    if intent.unresolved and client is not None:
        _llm_fallback_resolve(
            intent, player_input,
            list(avail_entities), list(avail_items), list(avail_locations), list(avail_hooks),
            client,
        )

    # Phase 3: action_type inference (deterministic, simple heuristics)
    intent.action_type = _infer_action_type(player_input)

    return intent


# ---------------------------------------------------------------------------
# Phase 1: deterministic alias matching
# ---------------------------------------------------------------------------


def _resolve_aliases_deterministic(
    player_input: str,
    known_entities: list[str],
    known_items: list[str],
    known_locations: list[str],
    known_hooks: list[str],
    known_motifs: list[str],
    aliases_map: dict[str, list[str]],
    avail_entities: set[str],
    avail_items: set[str],
    avail_locations: set[str],
    avail_hooks: set[str],
    avail_motifs: set[str],
) -> ResolvedIntent:
    """Build a flat alias index from known_universe and match against player input.

    Availability is determined by whether the canonical_id is in the
    corresponding available_* set.
    """
    text = player_input.strip().lower()
    intent = ResolvedIntent()

    # Build reverse index: alias phrase -> [(canonical_id, kind), ...]
    reverse_index: dict[str, list[tuple[str, str]]] = {}
    all_canonicals: list[tuple[str, str, list[str]]] = []

    for cid in known_entities:
        aliases = aliases_map.get(cid, [])
        all_canonicals.append((cid, "entity", aliases))
    for cid in known_items:
        aliases = aliases_map.get(cid, [])
        all_canonicals.append((cid, "item", aliases))
    for cid in known_locations:
        aliases = aliases_map.get(cid, [])
        all_canonicals.append((cid, "location", aliases))
    for cid in known_hooks:
        aliases = aliases_map.get(cid, [])
        all_canonicals.append((cid, "hook", aliases))
    for cid in known_motifs:
        aliases = aliases_map.get(cid, [])
        all_canonicals.append((cid, "motif", aliases))

    for cid, kind, aliases in all_canonicals:
        # Include canonical id itself (with spaces instead of underscores)
        all_phrases = [cid.replace("_", " ")] + [a.strip().lower() for a in aliases if a.strip()]
        for phrase in all_phrases:
            if phrase:
                reverse_index.setdefault(phrase, []).append((cid, kind))

    # Sort aliases by length descending so longer phrases match first
    sorted_aliases = sorted(reverse_index.keys(), key=len, reverse=True)

    matched_spans: list[tuple[int, int, str, str, float]] = []  # start, end, canonical_id, kind, confidence

    # Strategy A: exact phrase containment (longest first)
    for alias in sorted_aliases:
        start = text.find(alias)
        while start != -1:
            # Skip if this span overlaps with an existing higher-confidence match
            end = start + len(alias)
            if not _overlaps_with_higher_confidence(start, end, 0.85, matched_spans):
                for cid, kind in reverse_index[alias]:
                    matched_spans.append((start, end, cid, kind, 0.85 if len(alias) < len(text) else 0.95))
            start = text.find(alias, start + 1)

    # Deduplicate by canonical_id, keeping highest confidence
    best: dict[str, tuple[str, str, float]] = {}
    for _start, _end, cid, kind, conf in matched_spans:
        key = f"{cid}:{kind}"
        if key not in best or best[key][2] < conf:
            best[key] = (cid, kind, conf)

    # Classify matched refs into targets vs props and mark availability
    for cid, kind, conf in best.values():
        available = {
            "entity": cid in avail_entities,
            "item": cid in avail_items,
            "location": cid in avail_locations,
            "hook": cid in avail_hooks,
            "motif": cid in avail_motifs,
        }.get(kind, False)

        ref = ResolvedRef(
            mention=_extract_mention_span(text, cid, reverse_index),
            canonical_id=cid,
            kind=kind,
            confidence=conf,
            available=available,
        )
        if kind in ("location", "entity"):
            intent.targets.append(ref)
        else:
            intent.props.append(ref)

    # Anything not matched? For MVP, we mark the whole input as unresolved
    # if no matches were found. A more sophisticated approach would extract
    # noun phrases and check each.
    if not best:
        intent.unresolved.append(player_input)

    return intent


def _resolve_coreference(
    player_input: str,
    last_targets: list[ResolvedRef],
    player_location: str,
    known_entities: list[str],
    known_items: list[str],
    known_locations: list[str],
    known_hooks: list[str],
    known_motifs: list[str],
    aliases_map: dict[str, list[str]],
    avail_entities: set[str],
    avail_items: set[str],
    avail_locations: set[str],
    avail_hooks: set[str],
    avail_motifs: set[str],
) -> list[ResolvedRef]:
    """Contextual coreference resolution for pronouns, omitted subjects, and "that door".

    Rules:
    1. Pronouns 它/这个/那个 → most recent same-kind ref from last_targets (conf 0.75).
    2. Omitted subject + verb (e.g. 试着推开) → if last_targets had a location, reuse it.
    3. 那扇门/这扇门 → search known_universe for door-related IDs (conf 0.75).
    """
    text = player_input.strip().lower()
    refs: list[ResolvedRef] = []

    # Rule 1: pronouns
    pronouns = ("它", "这个", "那个")
    if any(p in text for p in pronouns):
        # Find most recent same-kind ref from last_targets
        for pronoun in pronouns:
            if pronoun in text:
                # Default to item/entity if ambiguous; prefer location if last was location
                for lt in reversed(last_targets):
                    kind = lt.kind
                    available = {
                        "entity": lt.canonical_id in avail_entities,
                        "item": lt.canonical_id in avail_items,
                        "location": lt.canonical_id in avail_locations,
                        "hook": lt.canonical_id in avail_hooks,
                        "motif": lt.canonical_id in avail_motifs,
                    }.get(kind, False)
                    refs.append(
                        ResolvedRef(
                            mention=pronoun,
                            canonical_id=lt.canonical_id,
                            kind=kind,
                            confidence=0.75,
                            available=available,
                        )
                    )
                    break
                break

    # Rule 2: omitted subject + movement/attack verb
    # If input starts with a verb and last_targets had a location, inherit it
    _OMITTED_VERBS = ("试着", "推", "打开", "走", "去", "进入", "移动", "尝试")
    if text.startswith(_OMITTED_VERBS) and not refs:
        for lt in reversed(last_targets):
            if lt.kind == "location":
                refs.append(
                    ResolvedRef(
                        mention=lt.mention,
                        canonical_id=lt.canonical_id,
                        kind="location",
                        confidence=0.75,
                        available=lt.canonical_id in avail_locations,
                    )
                )
                break

    # Rule 3: 那扇门 / 这扇门
    if "门" in text and not refs:
        door_keywords = ("门", "door", "gate")
        for cid in known_locations:
            if any(kw in cid for kw in door_keywords):
                aliases = aliases_map.get(cid, [])
                if any(kw in a for a in aliases for kw in door_keywords):
                    refs.append(
                        ResolvedRef(
                            mention="门",
                            canonical_id=cid,
                            kind="location",
                            confidence=0.75,
                            available=cid in avail_locations,
                        )
                    )
                    break
            # Also check aliases directly
            aliases = aliases_map.get(cid, [])
            for alias in aliases:
                if any(kw in alias for kw in door_keywords):
                    refs.append(
                        ResolvedRef(
                            mention="门",
                            canonical_id=cid,
                            kind="location",
                            confidence=0.75,
                            available=cid in avail_locations,
                        )
                    )
                    break
            if refs:
                break

    return refs


def _overlaps_with_higher_confidence(
    start: int, end: int, confidence: float, matched_spans: list[tuple[int, int, str, str, float]]
) -> bool:
    """Check if this span overlaps with an existing match of >= confidence."""
    for s, e, _cid, _kind, conf in matched_spans:
        if not (end <= s or start >= e):  # overlap
            if conf >= confidence:
                return True
    return False


def _extract_mention_span(text: str, canonical_id: str, reverse_index: dict[str, list[tuple[str, str]]]) -> str:
    """Try to find the alias phrase that maps to this canonical id."""
    for alias, candidates in reverse_index.items():
        for cid, _kind in candidates:
            if cid == canonical_id and alias in text:
                return alias
    return canonical_id.replace("_", " ")


# ---------------------------------------------------------------------------
# Phase 2: LLM fallback
# ---------------------------------------------------------------------------


def _llm_fallback_resolve(
    intent: ResolvedIntent,
    player_input: str,
    visible_entities: list[str],
    visible_items: list[str],
    reachable_locations: list[str],
    active_hooks: list[str],
    client: LlmClient,
) -> None:
    """Use local vLLM to resolve remaining mentions."""
    # Build context of available canonical IDs
    context = {
        "entities": visible_entities,
        "items": visible_items,
        "locations": reachable_locations,
        "hooks": active_hooks,
    }

    system_prompt = (
        "You are a Reference Resolver for a narrative RPG engine.\n"
        "Given player input and a list of available canonical IDs, "
        "identify which IDs the player is referring to.\n"
        "Output JSON only, no markdown fences.\n\n"
        "Rules:\n"
        "1. Only reference IDs from the provided lists.\n"
        "2. If the player refers to something not in the lists, output empty arrays.\n"
        "3. Output MUST be valid JSON."
    )

    user_prompt = json.dumps(
        {
            "player_input": player_input,
            "available_ids": context,
            "unresolved_phrases": intent.unresolved,
        },
        ensure_ascii=False,
        indent=2,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = client.chat_json(messages, temperature=0.2)
        resolved = raw.get("resolved", [])
        if isinstance(resolved, list):
            for r in resolved:
                if isinstance(r, dict) and r.get("canonical_id"):
                    ref = ResolvedRef(
                        mention=r.get("mention", ""),
                        canonical_id=r["canonical_id"],
                        kind=r.get("kind", "unknown"),
                        confidence=float(r.get("confidence", 0.7)),
                    )
                    if ref.confidence >= 0.7:
                        if ref.kind in ("location", "entity"):
                            intent.targets.append(ref)
                        else:
                            intent.props.append(ref)
                        # Remove from unresolved if present
                        if r.get("mention", "") in intent.unresolved:
                            intent.unresolved.remove(r["mention"])
                    # else: keep in unresolved (ambiguous)
        still_unresolved = raw.get("still_unresolved", [])
        if isinstance(still_unresolved, list):
            intent.unresolved = still_unresolved
    except Exception:
        # LLM fallback failed — keep unresolved as-is
        pass


# ---------------------------------------------------------------------------
# Phase 3: action type inference
# ---------------------------------------------------------------------------


def _infer_action_type(player_input: str) -> str:
    """Simple heuristic action type inference.

    Replaces the v0.7.0 hard-coded verb table with a broader
    but still deterministic classification.
    """
    text = player_input.lower().strip()

    # Talk / ask — checked first because verbs like 问 are unambiguous
    # even when the sentence also contains movement words (e.g. 问...下去)
    if any(v in text for v in ("问", "说", "告诉", "聊", "talk", "ask", "speak", "say", "tell")):
        return "speak"

    # Inspect / observe
    if any(v in text for v in ("看", "检查", "观察", "查看", "inspect", "check", "look", "examine", "search")):
        return "inspect"

    # Take / use item
    if any(v in text for v in ("拿", "取", "用", "使用", "给", "take", "use", "pick", "give", "hand")):
        return "interact"

    # Attack / force
    if any(v in text for v in ("打", "攻击", "杀", "推", "attack", "hit", "kill", "force", "push")):
        return "attack"

    # Movement — most generic, checked last
    if any(v in text for v in ("走", "去", "到", "接近", "靠近", "进入", "move", "go", "walk", "enter")):
        return "move"

    return "ambiguous"
