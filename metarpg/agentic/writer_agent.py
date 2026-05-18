"""Writer Agent — DeepSeek Flash (Bold) or local Qwen (Safe modes).

Interprets the player's action in local context and writes segmented
player-facing narrative with candidate patch effects.

Modes:
- bold              Flash, temperature 0.7-0.8, no feasibility ingestion.
                    Lives in parallel with Feasibility; failure is expected
                    when input is willful.
- safe_loose        Qwen, temperature 0.3, sees feasibility facts as soft
                    constraints. Bold prompt + facts.
- safe_strict_*     Qwen, temperature 0.3-0.5, each variant tied to one
                    world_response_kind. Templates are vibe guidance, not
                    task checklists.

Uses the canonical prompt from MetaRPG_Agent_story_prompt_reference.md.
"""
from __future__ import annotations

import json
from typing import Any

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import CandidatePatchEffect, FeasibilityReport, Segment, WriterOutput


class WriterOutputError(RuntimeError):
    """Raised when Writer output cannot be parsed, with raw text preserved."""

    def __init__(self, message: str, raw_text: str = "") -> None:
        super().__init__(message)
        self.raw_text = raw_text


_SYSTEM_PROMPT = """You are the Writer Agent for MetaRPG.

You write vivid, player-facing local adventure prose.
You are not the final authority on world state.
You propose candidate patch effects, assumptions, and segmented narrative.
The Committer decides what becomes canon after audit.

Your job:
1. Interpret the player's action in the given local story packet.
2. Write short, vivid narrative segments.
3. Propose candidate patch effects using only allowed effect kinds.
4. Declare assumptions explicitly.
5. Keep player-facing prose free of raw event ids, debug terms, belief percentages, and schema language.

Hard constraints:
- Do not let absent entities act, watch, speak, or react.
- Do not describe NPC inner thoughts as fact.
- Do not expose hidden facts unless allowed_reveals explicitly permits it.
- Do not invent new named NPCs, locations, objects, or hard facts unless candidate_patch includes an allowed effect for doing so.
- Do not make hard state changes only in prose.
- Every meaningful story segment must either reference candidate patch effects or be marked as pure sensory/transient.
- Keep the final narrative grounded in what the player can observe.

Style:
- Chinese prose.
- 1 to 4 short segments per turn.
- Concrete sensory detail is good.
- Do not over-explain trust, belief, probability, or system reasoning.
- Let mystery remain mystery.

FORMAT PRIORITY
- Your response must be one complete valid JSON object.
- The JSON must be parseable by Python json.loads without repair.
- Every object and array must be closed.
- Every property name must use double quotes.
- Every string must be closed before the next field begins.
- Do not stop in the middle of a field.
- If you are running out of space, shorten prose and close the JSON correctly.
- Prefer 2-3 complete segments over many incomplete segments.
- Do not include markdown fences.
- Do not include comments.

LENGTH CONTROL
- Write enough prose to make the player's action clear and playable.
- Prefer 2-3 complete segments.
- Each segment should be 1-3 sentences.
- Avoid adding extra objects, extra NPC actions, or extra assumptions just to be vivid.
- Completeness and parseability are more important than flourish.

LOCAL INVENTION RULE
- You may introduce small plausible local details only if they do not become hard facts.
- If you invent a concrete object in the player's possession, declare it in candidate_patch or mark it as an assumption requiring audit.
- If inventory_or_handheld is empty, do not state that the player already owns specific items unless candidate_patch proposes reveal_inventory or acquire_item.
- Tavern ambience may include generic smell, noise, warmth, cups, benches, and unnamed patrons.
- Named items, money, weapons, notes, keys, food in the player's pack, or NPC gifts must be represented in candidate_patch.

STOP CONDITION
Before finishing, mentally verify:
1. JSON starts with { and ends with }.
2. All arrays are closed.
3. All segment objects are closed.
4. candidate_patch is an array even if empty.
5. assumptions is an array even if empty.
6. risk_notes is an array even if empty.

TIME AWARENESS
The story_packet includes current_time. All NPC states must reflect time:
- Early morning (5–8): fresh, purposeful
- Morning (9–11): alert, working
- Noon (12–13): busy, focused, loud
- Afternoon (14–17): settled, talkative
- Evening (18–20): tired, reflective, slower
- Night (21–23): weary, cautious, quiet
- Late night (0–4): exhausted, irritable, close to sleep
NPC movement and dialogue pace should shift with these tones.

LORE CONFLICTS
If the story_packet marks a conflict between two accounts, you may:
- Let the NPC hesitate or deflect when asked
- Let the NPC subtly contradict their earlier statement
- Have another NPC challenge the account
Do not resolve the conflict unless the player explicitly uncovers evidence.

AMBIENT EVENTS
The story_packet may include ambient_events describing what happened
while the player was away. Weave these into the opening of your narrative
naturally, without making them the focus.
"""


_SAFE_LOOSE_PROMPT = _SYSTEM_PROMPT + """

SAFE MODE — LOOSE
You are running as the loose safety candidate.
FEASIBILITY CONTEXT (if present) lists facts you MUST respect in the prose.
preserve_player_voice lists key words you MUST surface in the narrative,
even if the action they describe fails in-world.
Stay in vivid local prose. Do not narrate refusals as the system's voice —
let the world push back through body, sound, and atmosphere.
"""


_SAFE_PROMPT_ABSENCE = _SYSTEM_PROMPT + """

SAFE MODE — ABSENCE
The player has invoked something that does not exist in this world.
Do NOT introduce that thing as if it were real.
Instead, let the absence be felt in the body and the room:
  - a gesture that reaches and finds nothing
  - a weight that should be in the hand and is not
  - a beat of silence where reality refuses the player's framing
NPCs may observe the misfire but should not name what isn't there.
preserve_player_voice words MUST appear in your prose, even if the action
they describe lands in empty space.
Do not write "this does not exist" or any system-level statement.
"""


_SAFE_PROMPT_FRICTION = _SYSTEM_PROMPT + """

SAFE MODE — FRICTION
The action is possible in principle, but the world resists.
Show resistance with concrete sensory weight:
  - a door that gives an inch and then locks itself again
  - an NPC who hears and turns, but withholds the answer
  - effort that costs more than the player thought
The player's voice (preserve_player_voice) must appear in some form.
Do not negate the action outright. Let the friction be the response.
"""


_SAFE_PROMPT_REFRAMING = _SYSTEM_PROMPT + """

SAFE MODE — REFRAMING
The player's framing of the action assumes a mechanism this world does
not have (telepathy, magic, modern technology). Re-anchor the action in
something this world DOES have:
  - reading minds becomes reading faces, posture, what eyes do not say
  - magic becomes ritual, herb, or a story whose truth is uncertain
  - tech becomes a tool or absence-of-a-tool with a craftsman's name
preserve_player_voice must still surface, even if the surrounding world
quietly translates it. Do not lecture the player on the swap.
"""


_SAFE_PROMPT_ACCEPT = _SYSTEM_PROMPT + """

SAFE MODE — ACCEPT
The input is feasible. Carry the scene gently:
  - take the player's stated action at face value
  - keep the segments short and grounded
  - if FEASIBILITY CONTEXT supplies facts, weave them in as background
preserve_player_voice words should appear naturally in the prose.
"""


_MODE_TO_PROMPT: dict[str, tuple[str, str]] = {
    "bold":               (_SYSTEM_PROMPT,         "flash"),
    "safe_loose":         (_SAFE_LOOSE_PROMPT,     "local"),
    "safe_strict_absence":   (_SAFE_PROMPT_ABSENCE,   "local"),
    "safe_strict_friction":  (_SAFE_PROMPT_FRICTION,  "local"),
    "safe_strict_reframing": (_SAFE_PROMPT_REFRAMING, "local"),
    "safe_strict_accept":    (_SAFE_PROMPT_ACCEPT,    "local"),
}


def _select_system_prompt(mode: str) -> tuple[str, str]:
    """Return (system_prompt, default_client_kind) for the requested mode."""
    if mode == "bold":
        # Identity-preserved for tests that compare against _SYSTEM_PROMPT.
        return _SYSTEM_PROMPT, "flash"
    if mode in _MODE_TO_PROMPT:
        return _MODE_TO_PROMPT[mode]
    raise ValueError(
        f"Unknown writer mode '{mode}'. Expected one of: {sorted(_MODE_TO_PROMPT)}"
    )


def _build_feasibility_block(feasibility: FeasibilityReport | None) -> str:
    """Render the facts + voice anchors as a user-prompt block. Empty if None."""
    if feasibility is None:
        return ""
    facts = feasibility.feasibility_facts or []
    voice = feasibility.preserve_player_voice or []
    if not facts and not voice:
        return ""
    parts = ["FEASIBILITY CONTEXT"]
    if facts:
        parts.append("feasibility_facts:")
        for f in facts:
            parts.append(f"  - {f}")
    if voice:
        parts.append("preserve_player_voice (words that MUST appear in prose):")
        parts.append("  " + ", ".join(voice))
    return "\n".join(parts) + "\n\n"


def _build_prompt(
    story_packet: dict[str, Any],
    player_input: str,
    feasibility: FeasibilityReport | None = None,
) -> str:
    feas_block = _build_feasibility_block(feasibility)
    return f"""{feas_block}STORY PACKET
{json.dumps(story_packet, ensure_ascii=False, indent=2)}

PLAYER INPUT
{player_input}

TASK
Write a local turn draft.

Return strict JSON only.

Required output schema:
{{
  "interpretation": "Plain-language interpretation of the player's action.",
  "segments": [
    {{
      "id": "s1",
      "type": "player_action | sensory | npc_observable_reaction | npc_speech | journal | transition",
      "text": "Player-facing Chinese prose.",
      "patch_refs": ["effect_kind:target_or_id"],
      "declared_claims": ["claim-like plain strings"],
      "transient_only": false
    }}
  ],
  "candidate_patch": [
    {{
      "kind": "transient_event | journal_note | observe_reaction | knowledge_transfer | relation_delta | belief_delta | move | add_fact | remove_fact | create_hook | consume_item | acquire_item | risk_flag | reveal",
      "args": {{}}
    }}
  ],
  "assumptions": [
    {{
      "claim": "What assumption you used.",
      "basis": "Where in the story packet this came from."
    }}
  ],
  "risk_notes": [
    "Any uncertainty or boundary you noticed."
  ]
}}

Do not include markdown.
Do not include explanations outside JSON.
"""


_REPAIR_PROMPT = """Your previous output is invalid JSON.
Fix JSON syntax only.
Do not change story content.
Do not add or remove story facts.
Do not improve prose.
Return one valid JSON object only.
It must parse with Python json.loads without repair.

JSON error:
{error}

Invalid output:
{raw}
"""


def safe_mode_for_kind(world_response_kind: str) -> str:
    """Map a feasibility world_response_kind to its safe_strict_* mode name."""
    kind = (world_response_kind or "accept").strip().lower()
    if kind not in {"absence", "friction", "reframing", "accept"}:
        kind = "accept"
    return f"safe_strict_{kind}"


def run_writer(
    story_packet: dict[str, Any],
    player_input: str,
    client: LlmClient | None = None,
    *,
    mode: str = "bold",
    feasibility: FeasibilityReport | None = None,
    temperature: float = 0.7,
) -> WriterOutput:
    """Call Writer LLM and parse output.

    mode selects both the system prompt and the default LLM kind. Pass a
    pre-built client to override the routing (the test capture client,
    or a pool slot).
    """
    system_prompt, default_kind = _select_system_prompt(mode)
    if client is None:
        client = make_client(default_kind)
    if client is None:
        raise RuntimeError(f"Writer LLM client unavailable (mode={mode})")

    prompt = _build_prompt(story_packet, player_input, feasibility=feasibility)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    raw_text = client.chat(messages, temperature=temperature)
    try:
        parsed = _parse_json_safe(raw_text)
    except Exception as first_exc:
        # One JSON syntax repair pass at temperature=0
        repair_msg = _REPAIR_PROMPT.format(error=str(first_exc), raw=raw_text[:4000])
        try:
            repair_text = client.chat(
                [
                    {"role": "system", "content": "You are a JSON repair tool. Fix syntax only."},
                    {"role": "user", "content": repair_msg},
                ],
                temperature=0.0,
                request_timeout=20.0,
            )
            parsed = _parse_json_safe(repair_text)
            raw_text = repair_text  # successful repair replaces raw for logging
        except Exception:
            raise WriterOutputError(str(first_exc), raw_text=raw_text) from first_exc

    segments = []
    for seg_data in parsed.get("segments", []):
        segments.append(
            Segment(
                id=seg_data.get("id", ""),
                type=seg_data.get("type", ""),
                text=seg_data.get("text", ""),
                patch_refs=seg_data.get("patch_refs", []),
                declared_claims=seg_data.get("declared_claims", []),
                transient_only=seg_data.get("transient_only", False),
            )
        )

    candidate_patch = []
    for eff_data in parsed.get("candidate_patch", []):
        candidate_patch.append(
            CandidatePatchEffect(
                kind=eff_data.get("kind", ""),
                args=eff_data.get("args", {}),
            )
        )

    return WriterOutput(
        interpretation=parsed.get("interpretation", ""),
        segments=segments,
        candidate_patch=candidate_patch,
        assumptions=parsed.get("assumptions", []),
        risk_notes=parsed.get("risk_notes", []),
        raw_json=parsed,
    )


def _parse_json_safe(text: str) -> dict[str, Any]:
    """Strip common wrappers and parse the first JSON object.

    Live LLMs occasionally add prose before/after the object, or return fenced
    JSON with whitespace around the fence. Keep this parser permissive while
    making failures diagnosable.
    """
    original = text
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            snippet = original[:800].replace("\n", "\\n")
            raise ValueError(f"Writer returned invalid JSON: {exc}. raw_prefix={snippet}") from exc

    snippet = original[:800].replace("\n", "\\n")
    raise ValueError(f"Writer returned no JSON object. raw_prefix={snippet}")
