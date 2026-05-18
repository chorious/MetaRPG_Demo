"""Refusal Fallback — template-based last-resort prose.

Used by runner when all Writer candidates (Bold + Safe_loose + Safe_strict)
fail audit. Generates a short, in-world refusal that:

- preserves the player's voice (echoes at least one word they used)
- is shaped by feasibility.world_response_kind
- never produces system terms ("absent", "hard_fail", etc.)
- yields only transient_event candidate_patch (no hard state change)

Expected trigger rate < 5%. This is a quality floor, not a primary path.
"""
from __future__ import annotations

from typing import Iterable

from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    FeasibilityReport,
    Segment,
    WriterOutput,
)


_KIND_TO_SEGMENTS: dict[str, tuple[str, str]] = {
    # (action_text, sensory_text) — '{voice}' will be replaced with player voice
    "absence": (
        "你的{voice}落在虚处。",
        "本该有的重量没有出现——像是空气替了某个本应存在的东西的位置。",
    ),
    "friction": (
        "你试着{voice}，世界回了一下手。",
        "动作没有被禁止,但被慢了下来。一种说不出的阻力贴在你的指节上。",
    ),
    "reframing": (
        "你想以{voice}的方式去理解眼前的事,却发现这个方式不太对。",
        "你转而依靠你能看到的、能听见的——它们没有告诉你你想要的答案,但也没有拒绝你。",
    ),
    "accept": (
        "你完成了{voice}这个动作。",
        "周围如常,没有什么需要立刻回应。你停在原地,等下一个念头浮上来。",
    ),
}


def _first_voice(voice: Iterable[str]) -> str:
    """Return the first non-empty voice token, or a neutral placeholder."""
    for v in voice:
        v = (v or "").strip()
        if v:
            return v
    return "这个动作"


def generate_segments(feasibility: FeasibilityReport | None) -> list[Segment]:
    """Build a 2-segment narrative for the refusal."""
    kind = "accept"
    voice_tokens: list[str] = []
    if feasibility is not None:
        kind = feasibility.world_response_kind or "accept"
        voice_tokens = list(feasibility.preserve_player_voice or [])

    action_tpl, sense_tpl = _KIND_TO_SEGMENTS.get(kind, _KIND_TO_SEGMENTS["accept"])
    voice = _first_voice(voice_tokens)

    action_text = action_tpl.replace("{voice}", voice)
    sense_text = sense_tpl.replace("{voice}", voice)

    return [
        Segment(
            id="rf1",
            type="player_action",
            text=action_text,
            patch_refs=["transient_event:refusal"],
            declared_claims=[],
            transient_only=True,
        ),
        Segment(
            id="rf2",
            type="sensory",
            text=sense_text,
            patch_refs=["transient_event:refusal"],
            declared_claims=[],
            transient_only=True,
        ),
    ]


def generate(feasibility: FeasibilityReport | None) -> WriterOutput:
    """Build a complete WriterOutput suitable for committing as transient-only."""
    segments = generate_segments(feasibility)
    kind = feasibility.world_response_kind if feasibility else "accept"
    patch = [
        CandidatePatchEffect(
            kind="transient_event",
            args={"name": f"refusal_{kind}", "description": "world-language refusal"},
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
