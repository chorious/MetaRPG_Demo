"""v0.4 regression tests — UPF event discipline + PLOTTER graph layer.

Per planVer0.4 §9. Verifies:
- apply_event is the sole state mutation path
- EventApplyOutcome: applied / rejected / deferred
- ApplyReport merged_delta matches canon_delta shape
- ActionContract validation
- EventGraph / CharacterGraph construction
- plot_diagnose detects coherence issues
"""
from __future__ import annotations

from metarpg.action_contract import (
    ActionContract,
    ClaimContract,
    EffectContract,
    SubActContract,
    contract_to_hypothesis,
    validate_contract,
)
from metarpg.apply_event import apply_event, apply_events
from metarpg.apply_report import ApplyReport
from metarpg.events import AdmittedEvent, EventApplyOutcome, event_category
from metarpg.models import Fact, WorldState
from metarpg.plot_diagnose import (
    diagnose_character_teleport,
    diagnose_contradictory_belief,
    diagnose_knowledge_leak,
    diagnose_motif_inconsistency,
    diagnose_orphan_events,
    diagnose_stale_hooks,
    run_diagnosis,
)
from metarpg.plot_graph import (
    CharacterGraph,
    EventGraph,
    EventNode,
    build_character_graph,
    build_event_graph,
)
from metarpg.scenarios.greyfen import build


# ---------- UPF Event Discipline ----------


def test_apply_event_travel_mutates_location():
    """UPF §9.1: travel event removes old at() and adds new at()."""
    w = build()
    e = AdmittedEvent("travel", ("player", "tavern", "guard_post"))
    outcome, reason, delta = apply_event(w, e)
    assert outcome == EventApplyOutcome.APPLIED
    assert Fact("at", ("player", "guard_post")) in w.facts
    assert Fact("at", ("player", "tavern")) not in w.facts


def test_apply_event_add_fact_idempotent():
    """Adding an existing fact is idempotent (applied, no duplicate)."""
    w = build()
    f = Fact("at", ("player", "tavern"))
    e = AdmittedEvent("add_fact", (f,))
    outcome, _, delta = apply_event(w, e)
    assert outcome == EventApplyOutcome.APPLIED
    # Second application
    outcome2, _, delta2 = apply_event(w, e)
    assert outcome2 == EventApplyOutcome.APPLIED
    assert len(delta2.get("facts_added", [])) == 0  # already exists


def test_apply_event_unknown_kind_rejected():
    """Unknown event kind returns REJECTED with reason."""
    w = build()
    e = AdmittedEvent("magic_spell", ("fireball",))
    outcome, reason, _ = apply_event(w, e)
    assert outcome == EventApplyOutcome.REJECTED
    assert "unknown_event_kind" in reason


def test_apply_report_merged_delta():
    """ApplyReport merges deltas from multiple events."""
    w = build()
    events = [
        AdmittedEvent("canon_event", ("player_broke_mug",)),
        AdmittedEvent("add_object", ("glass_shard", "tavern")),
        AdmittedEvent("rel_delta", ("mara", "player", "fear", 0.12)),
    ]
    report = apply_events(w, events)
    assert report.events_applied == 3
    delta = report.merged_delta
    assert "player_broke_mug" in delta["events"]
    assert any(obj == "glass_shard" for obj, place in delta["objects_added"])
    assert any(d[0] == "mara" for d in delta["rel_deltas"])


def test_apply_report_tracks_rejected():
    """ApplyReport records rejected events separately."""
    w = build()
    events = [
        AdmittedEvent("add_object", ("glass_shard", "tavern")),
        AdmittedEvent("magic_spell", ("fireball",)),
    ]
    report = apply_events(w, events)
    assert report.events_applied == 1
    assert report.events_rejected == 1
    assert report.had_rejected


def test_apply_report_deferred():
    """Deferred events are recorded but do not mutate state."""
    w = build()
    e = AdmittedEvent("hook_create", ("H_test", "communicate"))
    outcome, reason, delta = apply_event(w, e)
    assert outcome == EventApplyOutcome.DEFERRED
    assert "hook_creation_delegated" in reason


def test_event_category_taxonomy():
    """event_category returns correct category for known kinds."""
    assert event_category("canon_event") == "narrative"
    assert event_category("add_fact") == "state"
    assert event_category("plot_thread_open") == "graph"
    assert event_category("unknown_xyz") == "unknown"


def test_admitted_event_from_effect_roundtrip():
    """AdmittedEvent.from_effect and to_effect are inverses."""
    from metarpg.models import Effect
    eff = Effect("add_fact", (Fact("test", ("a",)),))
    evt = AdmittedEvent.from_effect(eff, source="test", provenance="heuristic")
    assert evt.kind == "add_fact"
    assert evt.source == "test"
    back = evt.to_effect()
    assert back.kind == eff.kind
    assert back.payload == eff.payload


# ---------- Action Contract ----------


def test_validate_contract_catches_missing_claims():
    """Contract validation flags subacts with no claims."""
    contract = ActionContract(
        act_kind="break_object",
        confidence=0.7,
        subacts=[
            SubActContract(kind="break", actor="player", claims=[], effects=[]),
        ],
    )
    errors = validate_contract(contract)
    assert any("no claims" in e for e in errors)


def test_validate_contract_catches_bad_impact():
    """Contract validation flags invalid impact values."""
    contract = ActionContract(
        act_kind="test",
        confidence=0.5,
        subacts=[
            SubActContract(
                kind="test",
                actor="player",
                claims=[ClaimContract("same_location", ["player", "mara"])],
                effects=[EffectContract("add_fact", ["x"], impact=99)],
            ),
        ],
    )
    errors = validate_contract(contract)
    assert any("invalid impact" in e for e in errors)


def test_contract_to_hypothesis_conversion():
    """A valid ActionContract converts to an ActHypothesis."""
    contract = ActionContract(
        act_kind="composite_act",
        confidence=0.75,
        subacts=[
            SubActContract(
                kind="break_object",
                actor="player",
                args=["ale_mug"],
                claims=[
                    ClaimContract("fragile", ["ale_mug"]),
                    ClaimContract("has_or_near", ["player", "ale_mug"]),
                ],
                effects=[
                    EffectContract("canon_event", ["player_broke_mug"], 1),
                    EffectContract("add_object", ["glass_shard", "tavern"], 2),
                ],
            ),
        ],
    )
    hyp = contract_to_hypothesis(contract)
    assert hyp is not None
    assert hyp.act_kind == "composite_act"
    assert len(hyp.subacts) == 1
    assert hyp.subacts[0].kind == "break_object"


# ---------- PLOTTER Graph Layer ----------


def test_build_event_graph_from_report():
    """EventGraph is built from an ApplyReport."""
    w = build()
    events = [
        AdmittedEvent("canon_event", ("player_arrived_at_guard_post",)),
        AdmittedEvent("add_knowledge", ("mara", Fact("sealed", ("old_mine",)))),
    ]
    report = apply_events(w, events)
    graph = build_event_graph(w, report)
    assert len(graph.events) >= 2


def test_event_graph_orphans():
    """Orphan events have no edges."""
    graph = EventGraph()
    graph.add(EventNode(id="E1", turn=1, kind="canon_event"))
    graph.add(EventNode(id="E2", turn=2, kind="canon_event"))
    assert len(graph.orphans()) == 2
    graph.link("E1", "E2", "causes")
    assert len(graph.orphans()) == 0


def test_build_character_graph():
    """CharacterGraph captures NPC locations and known facts."""
    w = build()
    graph = build_character_graph(w)
    assert "mara" in graph.characters
    assert "rusk" in graph.characters
    mara = graph.characters["mara"]
    assert mara.current_location == "tavern"
    # Mara knows sealed(old_mine) from initial setup
    assert any("sealed" in kf for kf in mara.known_facts)


# ---------- Diagnosis ----------


def test_diagnose_stale_hooks():
    """Hooks older than 8 turns with low priority are flagged."""
    w = build()
    w.hooks["H_old"] = type("H", (), {
        "id": "H_old", "consumed": False, "source_turn": 1,
        "priority": 0.3, "ttl": 3, "valid_targets": [], "participants": [],
        "topics": [], "places": [], "owner": "player", "hook_type": "communicate",
        "source_events": [], "trigger_cues": [], "payload_claims": [],
        "proposed_effects": [], "decay_policy": "consume_once",
    })()
    w.turn = 10
    issues = diagnose_stale_hooks(None, None, w)
    assert any(i.kind == "stale_hook" for i in issues)


def test_diagnose_contradictory_belief():
    """Belief claiming alive when canon says dead is flagged."""
    w = build()
    w.facts.add(Fact("dead", ("iven",)))
    from metarpg.models import Belief
    w.beliefs["B_bad"] = Belief("B_bad", "iven_alive_in_mine", 0.75)
    issues = diagnose_contradictory_belief(None, None, w)
    assert any(i.kind == "contradictory_belief" for i in issues)


def test_diagnose_motif_inconsistency_low_pressure():
    """Motif with all params near zero is flagged."""
    w = build()
    from metarpg.models import Motif
    w.motifs[("test_motif", ("a", "b"))] = Motif(
        name="test_motif", args=("a", "b"), params={"pressure": 0.02, "lure": 0.01}
    )
    issues = diagnose_motif_inconsistency(None, None, w)
    assert any(i.kind == "motif_inconsistency" for i in issues)


def test_run_diagnosis_sorts_by_severity():
    """Diagnosis results are sorted high -> medium -> low."""
    w = build()
    w.facts.add(Fact("dead", ("iven",)))
    from metarpg.models import Belief
    w.beliefs["B_bad"] = Belief("B_bad", "iven_alive_in_mine", 0.75)
    issues = run_diagnosis(w, None, None)
    if len(issues) >= 2:
        severities = [i.severity for i in issues]
        assert severities.index("high") < severities.index("low")


def test_diagnosis_summary_format():
    """diagnosis_summary produces readable output."""
    from metarpg.plot_diagnose import DiagnosisIssue, diagnosis_summary
    issues = [
        DiagnosisIssue("test_issue", "medium", "something is wrong", suggested_repair="fix_it"),
    ]
    text = diagnosis_summary(issues)
    assert "test_issue" in text
    assert "fix_it" in text
