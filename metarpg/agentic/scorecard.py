"""Scorecard for agentic turn evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnScorecard:
    turn_id: str = ""
    grounding_score: float = 0.0
    patch_alignment_score: float = 0.0
    hidden_leak_count: int = 0
    absent_entity_action_count: int = 0
    raw_debug_exposure_count: int = 0
    unsupported_claim_rate: float = 0.0
    unregistered_state_change_count: int = 0
    action_understanding_score: float = 0.0
    rewrite_locality_score: float = 0.0
    player_experience_score: float = 0.0
    repair_rounds: int = 0
    token_cost_estimate: int = 0
    latency_ms: int = 0
    hard_failures: list[str] = field(default_factory=list)
    medium_issues: list[str] = field(default_factory=list)
    soft_issues: list[str] = field(default_factory=list)
    hard_issue_count: int = 0
    medium_issue_count: int = 0
    soft_issue_count: int = 0
    notes: list[str] = field(default_factory=list)
    missing_player_output: bool = False
    missing_turn_sequence: bool = False
    state_continuity_score: float = 0.0
    packet_support_score: float = 0.0

    def to_json(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    def is_acceptable(self) -> bool:
        return (
            self.hidden_leak_count == 0
            and self.absent_entity_action_count == 0
            and self.raw_debug_exposure_count == 0
            and self.unregistered_state_change_count == 0
            and len(self.hard_failures) == 0
            and not self.missing_player_output
        )

    def compute_player_experience(self) -> float:
        """Compute capped player experience score based on issue severities."""
        if self.missing_player_output:
            return 0.0
        score = 1.0
        if self.hard_failures:
            score = 0.0
        elif self.medium_issues:
            score = min(score, 0.75)
        elif self.soft_issues:
            score = min(score, 0.85)
        return score
