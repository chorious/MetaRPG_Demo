"""Apply report — v0.4.

Records what happened during event application.

Borrowed from UPF:
  - Applied / Rejected / Deferred outcome tracking
  - Merged delta for canon-layer consumption
  - Source/provenance tracing
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .events import AdmittedEvent, EventApplyOutcome


@dataclass
class ApplyReport:
    """Record of event application outcomes.

    Consumers:
      - engine: reads merged_delta for canon_delta
      - hookgen: reads applied events to generate hooks
      - plot_graph: reads all outcomes for graph updates
      - renderer: reads applied events for narration
    """

    applied: list[tuple[AdmittedEvent, dict[str, Any]]] = field(default_factory=list)
    rejected: list[tuple[AdmittedEvent, str]] = field(default_factory=list)
    deferred: list[tuple[AdmittedEvent, str]] = field(default_factory=list)

    # Metrics
    events_processed: int = 0
    events_applied: int = 0
    events_rejected: int = 0
    events_deferred: int = 0

    def record(
        self,
        event: AdmittedEvent,
        outcome: EventApplyOutcome,
        reason: str,
        delta: dict[str, Any],
    ) -> None:
        """Record a single event application result."""
        self.events_processed += 1
        if outcome == EventApplyOutcome.APPLIED:
            self.applied.append((event, delta))
            self.events_applied += 1
        elif outcome == EventApplyOutcome.REJECTED:
            self.rejected.append((event, reason))
            self.events_rejected += 1
        elif outcome == EventApplyOutcome.DEFERRED:
            self.deferred.append((event, reason))
            self.events_deferred += 1

    @property
    def merged_delta(self) -> dict[str, Any]:
        """Merge all applied event deltas into a single canon_delta-like dict.

        Keys follow the same naming convention as world.apply_patch:
          events, transient_events, observations, rel_deltas, belief_deltas,
          facts_added, facts_removed, knowledge_added, motif_deltas,
          objects_added, objects_removed, risk_flags, attention_deltas, etc.
        """
        result: dict[str, Any] = {}
        for _, delta in self.applied:
            for key, value in delta.items():
                if key not in result:
                    result[key] = list(value) if isinstance(value, list) else value
                    continue
                if isinstance(value, list):
                    if isinstance(result[key], list):
                        result[key].extend(value)
                    else:
                        result[key] = [result[key], *value]
                else:
                    if isinstance(result[key], list):
                        result[key].append(value)
                    else:
                        result[key] = [result[key], value]
        return result

    @property
    def ok(self) -> bool:
        """True if at least one event was applied and nothing was rejected."""
        return self.events_applied > 0 and self.events_rejected == 0

    @property
    def had_deferred(self) -> bool:
        """True if any event was deferred."""
        return self.events_deferred > 0

    @property
    def had_rejected(self) -> bool:
        """True if any event was rejected."""
        return self.events_rejected > 0

    def summary(self) -> str:
        """Human-readable one-line summary."""
        parts = [f"processed={self.events_processed}"]
        if self.events_applied:
            parts.append(f"applied={self.events_applied}")
        if self.events_rejected:
            parts.append(f"rejected={self.events_rejected}")
        if self.events_deferred:
            parts.append(f"deferred={self.events_deferred}")
        return f"ApplyReport({', '.join(parts)})"
