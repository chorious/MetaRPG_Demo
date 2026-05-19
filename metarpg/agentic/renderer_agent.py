"""Renderer Agent — DeepSeek Flash generates player-facing Chinese prose.

The Renderer is the ONLY layer allowed to call DeepSeek Flash.
It receives a RenderBrief and outputs final player text.
It must NOT commit world changes.
"""
from __future__ import annotations

from typing import Any

from metarpg.agentic.model_client import LlmClient
from metarpg.agentic.transaction import RenderBrief


def run_renderer(
    render_brief: RenderBrief,
    story_packet: dict[str, Any],
    client: LlmClient,
) -> str:
    """Generate player-facing prose from a RenderBrief.

    Args:
        render_brief: Constraints and raw material for this turn's narrative.
        story_packet: Local visible context (scene, entities, items).
        client: DeepSeek Flash client (make_client("flash")).
    """
    system_prompt = _build_system_prompt(render_brief)
    user_prompt = _build_user_prompt(render_brief, story_packet)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    return client.chat(messages, temperature=0.8)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_system_prompt(brief: RenderBrief) -> str:
    return (
        "You are a narrative renderer for a Chinese-language RPG. "
        "Your only job is to turn structured story briefs into evocative, "
        "restrained, sensory Chinese prose for the player.\n\n"
        "Rules:\n"
        "1. Write in Chinese (zh).\n"
        "2. Do NOT add new world facts that are not in the brief.\n"
        "3. Do NOT reveal hidden truths.\n"
        "4. Do NOT write NPC inner monologue.\n"
        "5. Use the provided motifs with concrete, varied sensory detail.\n"
        "6. Player inner monologue is allowed if it fits the moment.\n"
        "7. Output ONLY the narrative text. No system terms, no meta commentary.\n"
    )


def _build_user_prompt(brief: RenderBrief, story_packet: dict[str, Any]) -> str:
    parts = [
        "## Scene",
        str(story_packet.get("scene", {})),
        "## Recent Events",
        "\n".join(brief.committed_events) or "None",
        "## Allowed Hints",
        "\n".join(brief.allowed_hints) or "None",
        "## Motifs to Use",
        "\n".join(brief.motifs_to_render) or "None",
        "## Forbidden",
        "\n".join(brief.forbidden_claims) or "None",
        "## Output",
        "Write 1–3 short paragraphs of Chinese prose.",
    ]
    return "\n\n".join(parts)
