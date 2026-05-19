"""Render Repair — one-shot prose repair via Flash (v0.7.3 Phase 3).

When post-render checker flags critical issues (L2 reject or hidden-truth
non-pass), this module attempts a one-shot rewrite to fix them.
"""
from __future__ import annotations

from metarpg.agentic.model_client import LlmClient
from metarpg.agentic.transaction import RenderBrief


_SYSTEM_PROMPT = (
    "You are a narrative repair editor for a Chinese-language RPG.\n"
    "Given the original prose and a list of issues, rewrite the prose to fix ALL issues.\n\n"
    "Repair rules:\n"
    "1. Preserve only committed events and visible entities.\n"
    "2. Remove unsupported entity/action/location claims.\n"
    "3. Remove symbolic hidden-truth hints named in issues.\n"
    "4. Keep 1-2 short Chinese paragraphs.\n"
    "5. Do not add new facts.\n"
    "6. Output ONLY the repaired narrative text.\n"
)


def run_render_repair(
    original_prose: str,
    issues: list[str],
    semantic_judgments: list[dict],
    render_brief: RenderBrief,
    client: LlmClient,
) -> str:
    """Attempt one-shot repair of failed prose.

    Returns the repaired prose string. Caller must re-run checker.
    """
    user_prompt = _build_repair_user_prompt(
        original_prose, issues, semantic_judgments, render_brief
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return client.chat(messages, temperature=0.5)


def _build_repair_user_prompt(
    original_prose: str,
    issues: list[str],
    semantic_judgments: list[dict],
    render_brief: RenderBrief,
) -> str:
    parts = [
        "## Original Prose",
        original_prose,
        "## Issues to Fix",
        "\n".join(f"- {i}" for i in issues) or "None",
        "## Semantic Judgments",
        "\n".join(f"- {j.get('check')}: {j.get('verdict')} ({j.get('category')})" for j in semantic_judgments) or "None",
        "## Committed Events (preserve only these)",
        "\n".join(render_brief.committed_events) or "None",
        "## Visible Entities (may describe)",
        "\n".join(render_brief.visible_entities) or "None",
        "## Absent Entities (must NOT place in scene)",
        "\n".join(render_brief.absent_entities) or "None",
        "## Player Location",
        render_brief.player_location or "Unknown",
        "## Allowed Hints",
        "\n".join(render_brief.allowed_hints) or "None",
        "## Output",
        "Write the repaired Chinese prose. Fix all issues while keeping the narrative evocative.",
    ]
    return "\n\n".join(parts)
