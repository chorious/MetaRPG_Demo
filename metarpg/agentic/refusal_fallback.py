"""Refusal Fallback — LLM-powered inner monologue (v0.6.6.1).

Used by runner when all Writer candidates fail audit. Generates a short,
player-facing inner monologue that:

- is shaped by feasibility.world_response_kind (absence/friction/reframing/accept)
- never produces system terms ("absent", "hard_fail", etc.)
- yields only transient_event candidate_patch (no hard state change)
- uses Flash LLM for quality (template fallback when Flash unavailable)

Expected trigger rate < 5%. This is a quality floor, not a primary path.
"""
from __future__ import annotations

from metarpg.agentic.model_client import LlmClient, make_client
from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    FeasibilityReport,
    Segment,
    WriterOutput,
)


_SYSTEM_PROMPT = """You are a fallback narrator for an RPG world.

All three Writer candidates failed audit. Your job: write 1-2 short segments
of PLAYER INNER MONOLOGUE that salvage the turn. Do NOT invent new facts,
new locations, or new NPCs. Stay inside what the world already knows.

Voice rules:
- First-person stream of consciousness (the player's own thoughts).
- Chinese prose, concrete sensory detail.
- No system terms, no meta-commentary, no "hard_fail" vocabulary.
- End with a clean JSON object.

Response format:
{
  "segments": [
    {"id": "rf1", "type": "inner_monologue", "text": "..."},
    {"id": "rf2", "type": "sensory", "text": "..."}
  ],
  "candidate_patch": [
    {"kind": "transient_event", "args": {"name": "refusal", "description": "..."}}
  ]
}
"""


_VIBE_BY_KIND: dict[str, str] = {
    "absence": "The player's intention hit nothing. Let the absence be felt in the body: a gesture that finds no weight, a breath that hangs too long.",
    "friction": "The world pushed back. Not a refusal, but a resistance: a door that gives an inch and stops, a look that withholds.",
    "reframing": "The player's framing doesn't fit this world. Let the mind quietly adjust, finding another way to read the same scene.",
    "accept": "The action completed but the world barely stirred. A quiet aftermath, the player alone with their own echo.",
}


def _build_prompt(
    feasibility: FeasibilityReport | None,
    recent_player_input: str,
    story_packet_summary: str = "",
) -> str:
    kind = feasibility.world_response_kind if feasibility else "accept"
    voice = ", ".join(feasibility.preserve_player_voice) if feasibility and feasibility.preserve_player_voice else recent_player_input[:20]
    vibe = _VIBE_BY_KIND.get(kind, _VIBE_BY_KIND["accept"])
    facts = "\n".join(f"- {f}" for f in (feasibility.feasibility_facts if feasibility else []))

    return f"""PLAYER INPUT
{recent_player_input}

WORLD RESPONSE KIND
{kind}

VIBE GUIDANCE
{vibe}

MUST-PRESERVE WORDS FROM PLAYER INPUT
{voice}

FEASIBILITY FACTS
{facts}

{story_packet_summary}

TASK
Write 1-2 segments of player inner monologue. Return strict JSON only.
"""


def generate(
    feasibility: FeasibilityReport | None,
    recent_player_input: str = "",
    story_packet_summary: str = "",
    client: LlmClient | None = None,
) -> WriterOutput:
    """Build a complete WriterOutput via LLM inner monologue.

    Falls back to code-only template if LLM is unavailable.
    """
    if client is None:
        client = make_client("flash")

    if client is not None:
        try:
            return _generate_llm(
                feasibility, recent_player_input, story_packet_summary, client
            )
        except Exception:
            pass  # fall through to template

    # Template fallback when LLM fails or is unavailable
    return _generate_template(feasibility)


def _generate_llm(
    feasibility: FeasibilityReport | None,
    recent_player_input: str,
    story_packet_summary: str,
    client: LlmClient,
) -> WriterOutput:
    prompt = _build_prompt(feasibility, recent_player_input, story_packet_summary)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    raw = client.chat(messages, temperature=0.5)
    parsed = _parse_json_safe(raw)

    segments = []
    for seg_data in parsed.get("segments", []):
        segments.append(
            Segment(
                id=seg_data.get("id", "rf1"),
                type=seg_data.get("type", "inner_monologue"),
                text=seg_data.get("text", ""),
                patch_refs=[],
                declared_claims=[],
                transient_only=True,
            )
        )

    if not segments:
        # LLM returned empty segments — fall back to template
        raise RuntimeError("LLM returned empty segments")

    patch = [
        CandidatePatchEffect(
            kind="transient_event",
            args={"name": "refusal_fallback", "description": "inner monologue fallback"},
        )
    ]

    return WriterOutput(
        interpretation=f"refusal_fallback:inner_monologue",
        segments=segments,
        candidate_patch=patch,
        assumptions=[],
        risk_notes=["refusal_fallback:LLM"],
        raw_json=parsed,
    )


def _generate_template(feasibility: FeasibilityReport | None) -> WriterOutput:
    """Code-only fallback when LLM is unavailable."""
    kind = feasibility.world_response_kind if feasibility else "accept"
    voice = _first_voice(feasibility.preserve_player_voice if feasibility else [])

    _KIND_TO_TEXT: dict[str, tuple[str, str]] = {
        "absence": (
            f"你的{voice}落在虚处。",
            "本该有的重量没有出现——像是空气替了某个本应存在的东西的位置。",
        ),
        "friction": (
            f"你试着{voice}，世界回了一下手。",
            "动作没有被禁止，但被慢了下来。一种说不出的阻力贴在你的指节上。",
        ),
        "reframing": (
            f"你想以{voice}的方式去理解眼前的事，却发现这个方式不太对。",
            "你转而依靠你能看到的、能听见的——它们没有告诉你你想要的答案，但也没有拒绝你。",
        ),
        "accept": (
            f"你完成了{voice}这个动作。",
            "周围如常，没有什么需要立刻回应。你停在原地，等下一个念头浮上来。",
        ),
    }

    action_tpl, sense_tpl = _KIND_TO_TEXT.get(kind, _KIND_TO_TEXT["accept"])
    action_text = action_tpl.replace("{voice}", voice)
    sense_text = sense_tpl.replace("{voice}", voice)

    segments = [
        Segment(
            id="rf1", type="inner_monologue", text=action_text,
            patch_refs=[], declared_claims=[], transient_only=True,
        ),
        Segment(
            id="rf2", type="sensory", text=sense_text,
            patch_refs=[], declared_claims=[], transient_only=True,
        ),
    ]
    patch = [
        CandidatePatchEffect(
            kind="transient_event",
            args={"name": f"refusal_{kind}", "description": "template fallback"},
        )
    ]
    return WriterOutput(
        interpretation=f"refusal_fallback:{kind}",
        segments=segments,
        candidate_patch=patch,
        assumptions=[],
        risk_notes=[f"refusal_fallback_template:{kind}"],
        raw_json=None,
    )


def _first_voice(voice: list[str]) -> str:
    for v in voice:
        v = (v or "").strip()
        if v:
            return v
    return "这个动作"


def _parse_json_safe(text: str) -> dict:
    import json
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found")
