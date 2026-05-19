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

    # Normalize move_player params: target_location -> destination
    for op in ops:
        if op.kind == "move_player" and "target_location" in op.params and "destination" not in op.params:
            op.params["destination"] = op.params.pop("target_location")

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
