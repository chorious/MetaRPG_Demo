"""Graph diagnosis — v0.4.

PLOTTER-style Evaluate-Plan-Revise cycle over EventGraph and CharacterGraph.

Evaluate: detect coherence issues.
Plan:     propose low-risk repairs.
Revise:   apply only safe structural cleanup; emit high-risk proposals.

Diagnostics are concrete and test-driven:
  knowledge_leak, character_teleport, orphan_event, stale_hook,
  contradictory_belief, motif_inconsistency
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import WorldState
from .plot_graph import CharacterGraph, EventGraph


@dataclass
class DiagnosisIssue:
    """One detected coherence issue."""

    kind: str
    severity: str  # low, medium, high
    description: str
    involved: list[str] = field(default_factory=list)
    suggested_repair: str = ""


# ---------- evaluate phase ----------


def diagnose_knowledge_leak(graph: EventGraph, chars: CharacterGraph, world: WorldState) -> list[DiagnosisIssue]:
    """Detect events where a character reacts to a fact they shouldn't know yet."""
    issues: list[DiagnosisIssue] = []

    for node in graph.events.values():
        if not node.admitted:
            continue
        for participant in node.participants:
            char = chars.characters.get(participant)
            if char is None:
                continue
            # Check if event implies knowledge the character lacks
            for topic in node.topics:
                known = any(topic in kf for kf in char.known_facts)
                if not known and node.kind in ("add_knowledge", "belief_delta"):
                    issues.append(DiagnosisIssue(
                        kind="knowledge_leak",
                        severity="medium",
                        description=f"{participant} may react to {topic} without known prior knowledge",
                        involved=[participant, topic],
                        suggested_repair="create_missing_communication_hook or downgrade_reaction",
                    ))
    return issues


def diagnose_character_teleport(graph: EventGraph, chars: CharacterGraph, world: WorldState) -> list[DiagnosisIssue]:
    """Detect events where a character acts in a location they are not present."""
    issues: list[DiagnosisIssue] = []

    for node in graph.events.values():
        if not node.admitted:
            continue
        for participant in node.participants:
            char = chars.characters.get(participant)
            if char is None:
                continue
            if node.location and char.current_location != node.location:
                # Exception: knowledge/information events can cross location
                if node.kind not in ("add_knowledge", "belief_delta", "dialogue"):
                    issues.append(DiagnosisIssue(
                        kind="character_teleport",
                        severity="high",
                        description=f"{participant} acts at {node.location} but is at {char.current_location}",
                        involved=[participant, node.location, char.current_location],
                        suggested_repair="reject_event or add_travel_event_first",
                    ))
    return issues


def diagnose_orphan_events(graph: EventGraph, _chars: CharacterGraph, _world: WorldState) -> list[DiagnosisIssue]:
    """Detect events with no causal connection to the narrative graph."""
    issues: list[DiagnosisIssue] = []
    orphans = graph.orphans()
    for node in orphans:
        if node.admitted and node.kind not in ("transient_event", "observe"):
            issues.append(DiagnosisIssue(
                kind="orphan_event",
                severity="low",
                description=f"Event {node.id} ({node.kind}) has no causes or consequences",
                involved=[node.id],
                suggested_repair="link_to_source_hook or allow_decay",
            ))
    return issues


def diagnose_stale_hooks(_graph: EventGraph, _chars: CharacterGraph, world: WorldState) -> list[DiagnosisIssue]:
    """Detect hooks that have been active for many turns without being touched."""
    issues: list[DiagnosisIssue] = []
    for hook in world.hooks.values():
        if hook.consumed:
            continue
        age = world.turn - hook.source_turn
        if age > 8 and hook.priority < 0.5:
            issues.append(DiagnosisIssue(
                kind="stale_hook",
                severity="low",
                description=f"Hook {hook.id} (age={age}, priority={hook.priority}) has decayed without use",
                involved=[hook.id],
                suggested_repair="decay_or_merge_hook",
            ))
        elif age > 12:
            issues.append(DiagnosisIssue(
                kind="stale_hook",
                severity="medium",
                description=f"Hook {hook.id} (age={age}) is very old and should expire",
                involved=[hook.id],
                suggested_repair="force_expire_hook",
            ))
    return issues


def diagnose_contradictory_belief(_graph: EventGraph, _chars: CharacterGraph, world: WorldState) -> list[DiagnosisIssue]:
    """Detect beliefs that conflict with hard canon facts."""
    issues: list[DiagnosisIssue] = []

    # Check: belief claims an entity is alive but canon says dead
    hard_alive = {f.args[0] for f in world.facts if f.predicate == "alive"}
    hard_dead = {f.args[0] for f in world.facts if f.predicate == "dead"}

    for bid, belief in world.beliefs.items():
        desc = belief.description.lower()
        if "alive" in desc or "dead" in desc:
            for entity in hard_dead:
                if entity in desc and "alive" in desc and belief.prob > 0.5:
                    issues.append(DiagnosisIssue(
                        kind="contradictory_belief",
                        severity="high",
                        description=f"Belief {bid} claims {entity} is alive but canon says dead",
                        involved=[bid, entity],
                        suggested_repair="cap_belief_probability or trigger_retrodiction",
                    ))
            for entity in hard_alive:
                if entity in desc and "dead" in desc and belief.prob > 0.5:
                    issues.append(DiagnosisIssue(
                        kind="contradictory_belief",
                        severity="high",
                        description=f"Belief {bid} claims {entity} is dead but canon says alive",
                        involved=[bid, entity],
                        suggested_repair="cap_belief_probability or trigger_retrodiction",
                    ))
    return issues


def diagnose_motif_inconsistency(_graph: EventGraph, _chars: CharacterGraph, world: WorldState) -> list[DiagnosisIssue]:
    """Detect active motifs with missing participants or no narrative pressure."""
    issues: list[DiagnosisIssue] = []

    for (mname, margs), motif in world.motifs.items():
        # Check if participants are still present in the world
        missing = [a for a in margs if a not in world.npcs and a != "player"]
        if missing:
            issues.append(DiagnosisIssue(
                kind="motif_inconsistency",
                severity="low",
                description=f"Motif {mname}{margs} references missing entities {missing}",
                involved=list(margs),
                suggested_repair="freeze_or_remove_motif",
            ))

        # Check if motif has any pressure (all params near zero)
        if motif.params and all(v < 0.1 for v in motif.params.values()):
            issues.append(DiagnosisIssue(
                kind="motif_inconsistency",
                severity="low",
                description=f"Motif {mname}{margs} has no narrative pressure (all params < 0.1)",
                involved=list(margs),
                suggested_repair="decay_or_remove_motif",
            ))

    return issues


# ---------- plan phase ----------


def plan_repairs(issues: list[DiagnosisIssue]) -> list[DiagnosisIssue]:
    """Attach concrete repair actions to each issue.

    Repairs are suggestions only; the caller decides what to apply.
    """
    for issue in issues:
        if issue.kind == "knowledge_leak":
            issue.suggested_repair = "create_missing_communication_hook"
        elif issue.kind == "character_teleport":
            issue.suggested_repair = "reject_or_defer_event"
        elif issue.kind == "orphan_event":
            issue.suggested_repair = "link_to_source_event_or_decay"
        elif issue.kind == "stale_hook":
            issue.suggested_repair = "decay_or_merge_hook"
        elif issue.kind == "contradictory_belief":
            issue.suggested_repair = "cap_probability_or_retrodict"
        elif issue.kind == "motif_inconsistency":
            issue.suggested_repair = "freeze_or_remove_motif"
    return issues


# ---------- main entry ----------


def run_diagnosis(
    world: WorldState,
    event_graph: EventGraph | None,
    char_graph: CharacterGraph | None,
) -> list[DiagnosisIssue]:
    """Run all diagnostic checks and return a prioritized list of issues."""
    issues: list[DiagnosisIssue] = []

    if event_graph and char_graph:
        issues.extend(diagnose_knowledge_leak(event_graph, char_graph, world))
        issues.extend(diagnose_character_teleport(event_graph, char_graph, world))
        issues.extend(diagnose_orphan_events(event_graph, char_graph, world))

    issues.extend(diagnose_stale_hooks(event_graph, char_graph, world))
    issues.extend(diagnose_contradictory_belief(event_graph, char_graph, world))
    issues.extend(diagnose_motif_inconsistency(event_graph, char_graph, world))

    # Plan repairs
    plan_repairs(issues)

    # Sort by severity
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: severity_rank.get(i.severity, 3))

    return issues


def diagnosis_summary(issues: list[DiagnosisIssue]) -> str:
    """Human-readable diagnosis summary."""
    if not issues:
        return "No issues detected."
    lines = [f"Diagnosis: {len(issues)} issue(s)"]
    for i in issues:
        lines.append(f"  [{i.severity}] {i.kind}: {i.description}")
        if i.suggested_repair:
            lines.append(f"    repair: {i.suggested_repair}")
    return "\n".join(lines)
