"""Expansion budget — v0.5.

Classifies player actions into budget tiers that control how much
world surface may be materialized in a single turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .frontier import Frontier, FrontierKind


class BudgetClass(Enum):
    """World mutation budget tiers."""

    NONE = "none"           # only parse/apply known action
    SMALL = "small"         # 1-3 affordances
    MEDIUM = "medium"       # 3-8 affordances
    LARGE = "large"         # scene entry / major discovery / crisis
    EMERGENCY = "emergency" # contradiction repair / state recovery


@dataclass
class Budget:
    """Budget allocation for a single turn."""

    class_: BudgetClass
    max_affordances: int
    max_hard_facts: int     # add_fact / add_object / remove_fact
    max_hooks: int
    max_soft_visible: int   # transient_event / observation

    def allows_hard_mutation(self) -> bool:
        return self.class_ in (BudgetClass.SMALL, BudgetClass.MEDIUM, BudgetClass.LARGE, BudgetClass.EMERGENCY)


# ---------- classification ----------


def classify_budget(action_text: str, touched_frontiers: list[Frontier]) -> Budget:
    """Classify a player action into a budget tier.

    Rules (heuristic, deterministic):
      - Scene boundary frontier -> large
      - Threat boundary / emergency -> emergency
      - Salient object / tool possibility -> medium
      - Known NPC dialogue / social tension -> small
      - No frontier touched -> none
    """
    text = action_text.lower()

    # Emergency keywords
    if any(k in text for k in ("矛盾", "contradiction", "修复", "repair", "崩溃", "crash")):
        return _budget(BudgetClass.EMERGENCY, 20, 5, 5, 10)

    # Check touched frontiers
    has_scene = any(f.kind == FrontierKind.SCENE_BOUNDARY for f in touched_frontiers)
    has_threat = any(f.kind == FrontierKind.THREAT_BOUNDARY for f in touched_frontiers)
    has_salient = any(f.kind == FrontierKind.SALIENT_OBJECT for f in touched_frontiers)
    has_tool = any(f.kind == FrontierKind.NEW_TOOL_POSSIBILITY for f in touched_frontiers)
    has_social = any(f.kind in (
        FrontierKind.UNQUERIED_NPC,
        FrontierKind.ACTIVE_SOCIAL_TENSION,
        FrontierKind.LATENT_HOOK,
    ) for f in touched_frontiers)

    if has_threat:
        return _budget(BudgetClass.LARGE, 12, 3, 3, 8)

    if has_scene:
        return _budget(BudgetClass.LARGE, 12, 3, 3, 8)

    if has_salient or has_tool:
        return _budget(BudgetClass.MEDIUM, 6, 2, 2, 4)

    if has_social:
        return _budget(BudgetClass.SMALL, 3, 1, 1, 2)

    # Movement cues (without explicit frontier)
    if any(k in text for k in ("去", "前往", "进入", "go", "enter", "move", "推门")):
        return _budget(BudgetClass.LARGE, 12, 3, 3, 8)

    # Object manipulation
    if any(k in text for k in ("找", "捡", "拿", "用", "find", "pick", "use", "拿")):
        return _budget(BudgetClass.MEDIUM, 6, 2, 2, 4)

    # Social action
    if any(k in text for k in ("问", "告诉", "说", "问", "ask", "tell", "talk", "说")):
        return _budget(BudgetClass.SMALL, 3, 1, 1, 2)

    return _budget(BudgetClass.NONE, 1, 0, 0, 1)


def _budget(
    class_: BudgetClass,
    max_aff: int,
    max_hard: int,
    max_hooks: int,
    max_soft: int,
) -> Budget:
    return Budget(
        class_=class_,
        max_affordances=max_aff,
        max_hard_facts=max_hard,
        max_hooks=max_hooks,
        max_soft_visible=max_soft,
    )


# Alias for cleaner imports
BudgetClass = BudgetClass
