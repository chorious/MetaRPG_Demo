"""Build RenderBrief from validated transaction, world diff, and narrative frame."""
from __future__ import annotations

from metarpg.agentic.transaction import NarrativeFrame, RenderBrief, TurnTransaction
from metarpg.models import WorldState


def build_render_brief(
    tx: TurnTransaction,
    frame: NarrativeFrame,
    world: WorldState,
) -> RenderBrief:
    """Assemble the brief that DeepSeek Flash will render into prose.

    Args:
        tx: The validated TurnTransaction (already committed).
        frame: The NarrativeFrame from HookManager.
        world: Current WorldState after commit (used to read recent events).
    """
    events = getattr(world, "events", [])
    recent_events = [
        e.get("summary", e.get("description", ""))
        for e in events[-3:]
        if e.get("summary") or e.get("description")
    ]

    return RenderBrief(
        committed_events=recent_events,
        visible_reactions=[],
        allowed_hints=list(frame.candidate_hints),
        motifs_to_render=list(frame.motifs_to_use),
        style_constraints=[],
        forbidden_claims=list(tx.forbidden_claims),
    )
