"""Director Agent — local vLLM outputs structured TurnTransaction (not prose).

Strategy (per v0.7.0 plan review):
1. Call model_client.chat_json() with tight system prompt.
2. Parse into Pydantic/dataclass.
3. Retry once with validation errors appended.
4. If still invalid, emit deterministic fallback transaction.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient
from metarpg.agentic.transaction import (
    Commitment,
    NarrativeFrame,
    Operation,
    TurnTransaction,
)


def run_director(
    player_input: str,
    narrative_frame: NarrativeFrame,
    story_packet: dict[str, Any],
    client: LlmClient,
    max_retries: int = 1,
) -> TurnTransaction:
    """Generate a TurnTransaction from player input + frame + context.

    Args:
        player_input: Raw player text.
        narrative_frame: Frame from HookManager (beat, hooks, motifs, etc.).
        story_packet: Local world context (scene, visible entities, etc.).
        client: local vLLM client (make_client("local")).
        max_retries: Number of retries after schema failure (default 1).
    """
    system_prompt = _build_system_prompt(narrative_frame)
    user_prompt = _build_user_prompt(player_input, narrative_frame, story_packet)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_raw: dict[str, Any] | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = client.chat_json(messages, temperature=0.4)
            last_raw = raw
            tx = _parse_transaction(raw)
            tx._director_raw = raw
            _coerce_ids(tx, narrative_frame)
            _validate_structure(tx, narrative_frame)
            return tx
        except Exception as exc:
            if attempt < max_retries:
                error_msg = (
                    f"Schema validation failed: {exc}\n"
                    "Please output strictly valid JSON matching the required schema. "
                    "No markdown fences, no extra text."
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(last_raw, ensure_ascii=False)
                        if last_raw is not None
                        else "",
                    }
                )
                messages.append({"role": "user", "content": error_msg})
            else:
                break

    return _fallback_transaction(player_input, narrative_frame)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_resolved_intent_payload(frame: NarrativeFrame) -> dict[str, Any]:
    """Build resolved_intent payload, handling both dict and str list formats."""
    if not (frame.resolved_targets or frame.resolved_props or frame.unresolved_mentions):
        return {}
    # v0.7.1 runner path: resolved_targets is list[dict]
    if frame.resolved_targets and isinstance(frame.resolved_targets[0], dict):
        return {
            "action_type": frame.resolved_targets[0].get("kind", ""),
            "targets": frame.resolved_targets,
            "props": frame.resolved_props,
            "unresolved": frame.unresolved_mentions,
        }
    # Legacy test path: resolved_targets is list[str]
    return {
        "action_type": "",
        "targets": [{"canonical_id": t, "kind": "unknown"} for t in frame.resolved_targets],
        "props": [{"canonical_id": p, "kind": "unknown"} for p in frame.resolved_props],
        "unresolved": frame.unresolved_mentions,
    }


def _build_system_prompt(frame: NarrativeFrame) -> str:
    return (
        "You are the Director of a narrative RPG engine.\n"
        "Your output is a structured TurnTransaction (JSON only, no prose).\n"
        "You decide what happens in the world, not how it is described to the player.\n\n"
        "Rules:\n"
        "1. Output MUST be valid JSON with no markdown code fences.\n"
        "2. Do NOT write player-facing prose.\n"
        "3. Do NOT reveal hidden truths directly.\n"
        "4. Do NOT write NPC inner monologue.\n"
        "5. Allowed operations: move_player, inspect, speak, observe_reaction, "
        "transfer_item, update_relation, update_belief, mark_hook_status, "
        "add_event, add_texture, inner_monologue.\n"
        f"6. Allowed commitment levels for this turn: {frame.allowed_commitment_levels}\n"
        f"7. Forbidden moves: {frame.forbidden_moves}\n\n"
        "COMMITMENT LEVEL GUIDE:\n"
        '- "canon": ONLY for hard state changes with definitive evidence. '
        "Examples: move_player succeeds, transfer_item completes, mark_hook_status changes.\n"
        '- "hint": Sensory observations, atmosphere, or indirect clues. '
        "Use this for descriptions of smells, sounds, textures, or suspicious behavior.\n"
        '- "belief_evidence": NPC reactions or behaviors that suggest inner state.\n'
        '- "utterance": Direct speech or paraphrased dialogue.\n'
        '- "texture": Pure atmosphere with no narrative claim.\n'
        '- "event": Factual turn summary (always safe).\n'
        '- "affordance": New item or interaction opportunity.\n\n'
        "BAD vs GOOD examples:\n"
        '- BAD canon: {"level": "canon", "description": "The door is sealed by magic"}\n'
        '- GOOD hint: {"level": "hint", "description": "The door resists force, suggesting supernatural sealing"}\n'
        '- BAD canon: {"level": "canon", "description": "Alen is afraid of the lower levels"}\n'
        '- GOOD belief_evidence: {"level": "belief_evidence", "description": "Alen flinches when the lower door is mentioned"}\n\n'
        "REQUIRED JSON SCHEMA:\n"
        '{\n'
        '  "player_input": "<original player text>",\n'
        '  "operations": [\n'
        '    {\n'
        '      "kind": "inspect",\n'
        '      "params": {"target": "black_ash", "description": "..."}\n'
        '    },\n'
        '    {\n'
        '      "kind": "speak",\n'
        '      "params": {"entity": "alen", "text": "..."}\n'
        '    },\n'
        '    {\n'
        '      "kind": "add_event",\n'
        '      "params": {"summary": "Player inspects ash"}\n'
        '    },\n'
        '    {\n'
        '      "kind": "mark_hook_status",\n'
        '      "params": {"hook_id": "hook_xxx", "status": "progressed"}\n'
        '    }\n'
        '  ],\n'
        '  "commitments": [\n'
        '    {"level": "event", "description": "Player inspects ash", "operation_index": 2},\n'
        '    {"level": "utterance", "description": "Alen says...", "operation_index": 1},\n'
        '    {"level": "hint", "description": "The ash smells odd", "operation_index": 0}\n'
        '  ],\n'
        '  "assumptions": []\n'
        '}\n\n'
        "IMPORTANT:\n"
        "- Each operation MUST have \"kind\" and nested \"params\".\n"
        "- \"commitments\" is a separate array describing narrative claims.\n"
        "- Use operation_index to link a commitment to its operation.\n"
    )


def _build_user_prompt(
    player_input: str,
    frame: NarrativeFrame,
    story_packet: dict[str, Any],
) -> str:
    payload = {
        "player_input": player_input,
        "beat": frame.beat,
        "active_hooks": frame.active_hooks,
        "candidate_hints": frame.candidate_hints,
        "motifs_to_use": frame.motifs_to_use,
        "dramatic_function": frame.dramatic_function,
        "allowed_commitment_levels": frame.allowed_commitment_levels,
        "forbidden_moves": frame.forbidden_moves,
        "scene": story_packet.get("scene", {}),
        "visible_entities": story_packet.get("scene", {}).get("visible_entities", []),
        "player_location": story_packet.get("player_context", {}).get("location", ""),
        # v0.7.1: canonical ID whitelist to prevent hallucinated IDs
        "canonical_id_whitelist": frame.canonical_id_whitelist,
        # v0.7.1: resolved intent from ReferenceResolver (L1)
        "resolved_intent": _build_resolved_intent_payload(frame),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Parse / validate
# ---------------------------------------------------------------------------


def _parse_transaction(raw: dict[str, Any]) -> TurnTransaction:
    """Parse Director JSON into TurnTransaction with schema tolerance.

    Handles common LLM deviations:
    - 'type' alias for 'kind'
    - Flat params (fields mixed into operation object instead of nested 'params')
    - 'commitment_level' inside operations instead of standalone 'commitments' array
    """
    raw_ops = raw.get("operations", [])
    if not isinstance(raw_ops, list):
        raise ValueError(f"'operations' must be a list, got {type(raw_ops).__name__}")

    ops: list[Operation] = []
    extracted_commitments: list[Commitment] = []

    for i, o in enumerate(raw_ops):
        if not isinstance(o, dict):
            continue
        kind = o.get("kind") or o.get("type", "")
        if not kind:
            continue

        # Collect params: prefer explicit 'params', else gather flat fields
        params = dict(o.get("params", {})) if "params" in o else {}
        if not params:
            reserved = {"kind", "type", "metadata", "commitment_level", "level", "description", "operation_index"}
            params = {k: v for k, v in o.items() if k not in reserved}

        ops.append(Operation(kind=kind, params=params))

        # Extract inline commitment_level
        level = o.get("commitment_level")
        if level:
            desc = params.get("description") or params.get("text") or params.get("content") or f"{kind} operation"
            extracted_commitments.append(
                Commitment(
                    level=level,
                    description=desc,
                    operation_index=i,
                    metadata={},
                )
            )

    # Standalone commitments array takes precedence over inline ones
    raw_commitments = raw.get("commitments", [])
    if raw_commitments:
        commitments = [
            Commitment(
                level=c["level"],
                description=c.get("description", ""),
                operation_index=c.get("operation_index", -1),
                metadata=c.get("metadata", {}),
            )
            for c in raw_commitments
            if isinstance(c, dict) and c.get("level")
        ]
    else:
        commitments = extracted_commitments

    # Normalize assumptions: strings -> dicts; skip non-dict items
    raw_assumptions = raw.get("assumptions", [])
    assumptions: list[dict[str, Any]] = []
    for a in raw_assumptions:
        if isinstance(a, dict):
            assumptions.append(a)
        elif isinstance(a, str):
            assumptions.append({"note": a})

    # Normalize move_player params: target_location / target -> destination
    for op in ops:
        if op.kind == "move_player":
            if "target_location" in op.params and "destination" not in op.params:
                op.params["destination"] = op.params.pop("target_location")
            if "target" in op.params and "destination" not in op.params:
                op.params["destination"] = op.params.pop("target")

    return TurnTransaction(
        player_input=raw.get("player_input", ""),
        operations=ops,
        commitments=commitments,
        assumptions=assumptions,
    )


def _validate_structure(tx: TurnTransaction, frame: NarrativeFrame) -> None:
    """Lightweight structural validation before returning."""
    allowed_levels = set(frame.allowed_commitment_levels)
    for c in tx.commitments:
        if c.level not in allowed_levels:
            raise ValueError(
                f"Commitment level {c.level!r} not in allowed {allowed_levels}"
            )

    for move in frame.forbidden_moves:
        for op in tx.operations:
            if move in op.kind or move in str(op.params):
                raise ValueError(
                    f"Forbidden move {move!r} detected in operation {op.kind}"
                )

    # v0.7.1: canonical ID whitelist validation (skip if not populated)
    whitelist = frame.canonical_id_whitelist
    if whitelist:
        active_hook_ids = set(whitelist.get("active_hook_ids", []))
        reachable_locs = set(whitelist.get("reachable_location_ids", []))
        visible_entities = set(whitelist.get("visible_entity_ids", []))

        for op in tx.operations:
            if op.kind == "mark_hook_status":
                hid = op.params.get("hook_id", "")
                if hid and active_hook_ids and hid not in active_hook_ids:
                    raise ValueError(
                        f"mark_hook_status hook_id {hid!r} not in active hooks. "
                        f"Allowed: {active_hook_ids}"
                    )
            if op.kind == "move_player":
                dest = op.params.get("destination", "")
                if not dest:
                    raise ValueError(
                        "move_player operation missing destination after normalization"
                    )
                if dest and reachable_locs and dest not in reachable_locs:
                    raise ValueError(
                        f"move_player destination {dest!r} not in reachable locations. "
                        f"Allowed: {reachable_locs}"
                    )
            visible_objects = set(whitelist.get("visible_objects", []))

            if op.kind == "speak":
                ent = op.params.get("entity", "")
                if ent and visible_entities and ent not in visible_entities:
                    raise ValueError(
                        f"speak entity {ent!r} not in visible entities. "
                        f"Allowed: {visible_entities}"
                    )
                if ent and visible_objects and ent in visible_objects:
                    raise ValueError(
                        f"speak entity {ent!r} is an object (visible_objects), not an entity. "
                        f"Objects cannot speak."
                    )

            if op.kind == "observe_reaction":
                ent = op.params.get("entity", "")
                if ent and visible_entities and ent not in visible_entities:
                    raise ValueError(
                        f"observe_reaction entity {ent!r} not in visible entities. "
                        f"Allowed: {visible_entities}"
                    )
                if ent and visible_objects and ent in visible_objects:
                    raise ValueError(
                        f"observe_reaction entity {ent!r} is an object (visible_objects), not an entity. "
                        f"Objects cannot react."
                    )


# ---------------------------------------------------------------------------
# ID coercion — use resolved intent to fix hallucinated IDs before validation
# ---------------------------------------------------------------------------


def _coerce_ids(tx: TurnTransaction, frame: NarrativeFrame) -> None:
    """Patch operations with canonical IDs from ReferenceResolver when Director hallucinates.

    Only fixes move_player.destination and speak.entity when the LLM invented an ID
    that is not in the whitelist but a resolved target of the correct kind exists.
    """
    if not frame.resolved_targets:
        return

    loc_targets = [
        r for r in frame.resolved_targets
        if isinstance(r, dict) and r.get("kind") == "location"
    ]
    ent_targets = [
        r for r in frame.resolved_targets
        if isinstance(r, dict) and r.get("kind") == "entity"
    ]

    whitelist = frame.canonical_id_whitelist or {}
    reachable_locs = set(whitelist.get("reachable_location_ids", []))
    visible_ents = set(whitelist.get("visible_entity_ids", []))

    for op in tx.operations:
        if op.kind == "move_player":
            dest = op.params.get("destination", "")
            if dest and reachable_locs and dest not in reachable_locs:
                if loc_targets:
                    op.params["destination"] = loc_targets[0]["canonical_id"]
        elif op.kind == "speak":
            ent = op.params.get("entity", "")
            if ent and visible_ents and ent not in visible_ents:
                if ent_targets:
                    op.params["entity"] = ent_targets[0]["canonical_id"]


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _fallback_transaction(
    player_input: str, frame: NarrativeFrame
) -> TurnTransaction:
    """Deterministic fallback when Director fails to produce valid JSON."""
    return TurnTransaction(
        player_input=player_input,
        operations=[
            Operation("inner_monologue", {"text": "Player hesitates."}),
            Operation("add_texture", {"text": "The moment hangs in the air."}),
        ],
        commitments=[
            Commitment(
                "texture",
                "A brief pause before action.",
                operation_index=1,
            )
        ],
        assumptions=[
            {"source": "fallback", "reason": "Director schema parse failed after retries"}
        ],
    )
