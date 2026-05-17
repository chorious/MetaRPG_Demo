# MetaRPG Dev v0.4 Plan - PLOTTER + STORY2GAME + UPF Fusion

## 0. Current Baseline

Current local project: `E:\GameDesign\MetaRPG_Dev`

Current code already includes:

```text
v0.2.1 admission control
v0.3 open meta-act hypothesis layer
v0.3.1 subject-bound event hooks
```

Current test state:

```text
127 passed
```

UPF has been cloned into:

```text
E:\GameDesign\MetaRPG_Dev\vendor\Unlimited_possibilies_framework
```

v0.4 should not rewrite the existing Python prototype. It should add a clean integration layer that borrows the strongest parts of:

```text
PLOTTER      -> graph-level narrative planning / diagnosis / revise
STORY2GAME   -> dynamic action generation via preconditions/effects
UPF          -> state-first RPG engine discipline + structured event protocol
Our engine    -> claims, hooks, belief, retrodiction, local reasonability
```

---

## 1. Source Mapping

### 1.1 PLOTTER / Planning Beyond Text

Source: `Planning Beyond Text: Graph-based Reasoning for Complex Narrative Generation`, arXiv:2604.21253.

Relevant design point:

```text
Narrative planning should happen on structural graph representations,
not only sequential text.
```

PLOTTER uses:

```text
Event Graph
Character Graph
Evaluate -> Plan -> Revise cycle
logical constraints over graph topology
```

Integration target for MetaRPG:

```text
Global narrative diagnosis layer
```

Do not run PLOTTER-style graph repair every turn. Run it as periodic diagnosis over:

```text
canon events
active hooks
character relations
belief/latent state
motifs
quest-like open threads
```

### 1.2 STORY2GAME

Source: `STORY2GAME: Generating (Almost) Everything in an Interactive Fiction Game`, arXiv:2505.03547.

Relevant design point:

```text
Hard-coded actions constrain play.
Generate actions with explicit preconditions and effects.
Dynamic action generation may require updating state representation and revising existing actions.
```

Integration target for MetaRPG:

```text
MetaAct -> ActionHypothesis -> support_claims/preconditions -> proposed_effects
```

Our terminology mapping:

```text
STORY2GAME preconditions  -> support_claims
STORY2GAME effects        -> proposed_effects / admitted effects
Dynamic action generation -> open MetaAct hypothesis proposal
State representation update -> schema/claim/object materialization admission
```

### 1.3 UPF / Unlimited Possibilities Framework

Source: `Gohzio/Unlimited_possibilies_framework`.

Relevant design point:

```text
State-first, not chat-first.
LLM proposes, engine applies.
All game changes are structured events.
State is inspectable and serialized.
```

UPF concrete reusable assets:

```text
src/model/narrative_event.rs      -> event protocol shape
src/model/event_result.rs         -> Applied / Rejected / Deferred outcome discipline
src/engine/apply_event.rs         -> authoritative event applier pattern
src/engine/prompt_builder.rs      -> prompt discipline + context request pattern
src/model/game_state.rs           -> RPG state snapshot concepts
README event schema               -> practical structured-output reference
```

UPF should be used as a reference/vendor, not blindly embedded. It is a Rust+egui app, while current MetaRPG core is Python CLI. Direct language-level integration now would slow iteration.

---

## 2. v0.4 Core Thesis

v0.4 is the first architecture where all layers are explicit:

```text
Player Text
  -> MetaAct
  -> Hook Match
  -> Dynamic Action Hypothesis      [STORY2GAME-style]
  -> Claim Validation
  -> Event Admission
  -> Authoritative State Apply      [UPF-style]
  -> Hook Generation / Belief Update / Retrodiction
  -> Event+Character Graph Update   [PLOTTER-style]
  -> Periodic Graph Diagnosis/Revise
  -> Renderer
```

The key boundary:

```text
LLM proposes hypotheses/events.
Claim validator admits consequences.
Event applier mutates state.
Graph planner diagnoses long-range coherence.
Renderer only narrates admitted state.
```

---

## 3. New v0.4 Components

### 3.1 `metarpg/events.py`

Introduce a UPF-inspired event protocol.

Do not replace current `Effect` immediately. Add an adapter layer:

```text
ProposedEffect -> AdmittedEvent -> StateDelta
```

Suggested event categories:

```text
Narrative-only:
  dialogue
  transient_event
  observation

State mutation:
  travel
  add_fact
  remove_fact
  add_knowledge
  add_object
  remove_object
  relationship_change
  belief_delta
  hook_create
  hook_consume
  hook_decay
  flag_set

Graph/planning:
  motif_activate
  motif_resolve
  plot_thread_open
  plot_thread_advance
  plot_thread_close
```

Borrow UPF outcome discipline:

```text
EventApplyOutcome:
  applied
  rejected(reason)
  deferred(reason)
```

Why `deferred` matters:

```text
Some generated action is plausible but needs missing context/object/target.
Do not reject forever; create a hook or ask for clarification.
```

### 3.2 `metarpg/apply_event.py`

Create a single authoritative event applier.

Current `world.apply_patch` mutates from effects directly. v0.4 should route through:

```text
admitted_events = admit_effects(hypothesis, claims)
apply_report = apply_events(world, admitted_events)
```

Rules:

```text
Only apply_event mutates WorldState.
Assembler may not directly mutate state.
Narrator may not mutate state.
Hook generator reads apply_report, not raw LLM text.
```

### 3.3 `metarpg/plot_graph.py`

PLOTTER-inspired structural graph layer.

Minimum graph types:

```text
EventNode:
  id, turn, kind, participants, location, topics, source_events

CharacterNode:
  id, traits, current_location, known_facts, active_goals, emotional_state

Edges:
  causes(event_a,event_b)
  reveals(event, fact)
  motivates(character,event_or_hook)
  blocks(event_or_fact, action_or_hook)
  knows(character,fact)
  tensions(character_a,character_b,topic)
```

Do not overbuild graph algorithms yet. Build extraction first.

### 3.4 `metarpg/plot_diagnose.py`

Run periodic graph diagnosis every N turns or via `/plot`.

PLOTTER-style Evaluate phase checks:

```text
causal orphan: important event has no cause or consequence
character teleport: entity acts where not present
knowledge leak: character reacts to unknown fact
unresolved hook overload: too many hooks on same topic
stale thread: plot thread decays without resolution
contradictory belief/canon: soft belief conflicts with hard fact
motif inconsistency: active motif has no participants or no pressure
```

Plan phase proposes repairs:

```text
create_hook
merge_hooks
defer_event
request_context
retcon_candidate
open_plot_thread
close_stale_thread
```

Revise phase must not auto-mutate canon unless repair is low-risk. Most repairs become proposed events/hooks.

---

## 4. UPF Fusion Strategy

### 4.1 What To Directly Copy/Port

Port concepts and small structures, not the full app.

Recommended ports into Python:

```text
UPF EventApplyOutcome -> Python enum/dataclass
UPF NarrativeApplyReport -> ApplyReport
UPF narrative event categories -> MetaRPG AdmittedEvent taxonomy
UPF request_context -> MetaRPG deferred/context_request event
UPF request_retcon -> MetaRPG retrodict candidate path
UPF state snapshot discipline -> debug/export snapshot
```

### 4.2 What To Keep As Vendor Reference

Keep under:

```text
vendor/Unlimited_possibilies_framework
```

Use it for:

```text
schema examples
prompt examples
state-first UI inspiration
event application patterns
save/audit strategy
```

Do not try to call Rust code from Python in v0.4.

### 4.3 Later Option: Rust Shell Around Python Core

If the project later needs UI/performance:

```text
Rust/egui shell from UPF
  -> Python MetaRPG core as local service or embedded process
```

But v0.4 should not spend time on GUI integration.

---

## 5. STORY2GAME Integration

### 5.1 Dynamic Action Proposal Contract

Add a strict structured output target for future LLM proposer:

```json
{
  "act_kind": "use_object_as_tool",
  "confidence": 0.73,
  "subacts": [
    {
      "kind": "find_object",
      "claims": [
        {"name": "plausible_scene_object", "args": ["loose_stone", "old_mine_gate"]}
      ],
      "effects": [
        {"kind": "add_object", "args": ["loose_stone", "old_mine_gate"], "impact": 2}
      ]
    },
    {
      "kind": "wedge_door",
      "claims": [
        {"name": "has_or_near", "args": ["player", "loose_stone"]},
        {"name": "can_block", "args": ["loose_stone", "old_mine_gate"]}
      ],
      "effects": [
        {"kind": "canon_event", "args": ["player_attempted_to_wedge_gate"], "impact": 1},
        {"kind": "add_fact", "args": ["blocked_open", "old_mine_gate"], "impact": 3}
      ]
    }
  ]
}
```

LLM output is not trusted. It is an action-code-generation analogue, but code validation replaces code execution.

### 5.2 State Representation Update

STORY2GAME notes that dynamic actions may require updating game state representation.

MetaRPG version:

```text
new object property claim appears
-> validate claim family
-> if allowed, add object tag/fact with provenance
-> if not allowed, defer/request context
```

Example:

```text
Claim: absorbent(rag)
If rag is plausible tavern object and absorbent is safe low-impact property:
  add_fact(property(rag,absorbent)) with provenance=dynamic_action
```

### 5.3 Do Not Generate Python Code Per Action Yet

STORY2GAME generates executable action code. For us, that is too risky and unnecessary in v0.4.

Use safer pipeline:

```text
LLM generates structured claims/effects
engine validates/adapts to event protocol
apply_event mutates state
```

---

## 6. PLOTTER Integration

### 6.1 Event Graph Construction

Every admitted event becomes graph data:

```text
event_id = E_turn_index
participants from event args / touched entities
location from player location or event args
topics from claims/effects/hooks
causal parents from source_events / triggered_hook / retropath
```

### 6.2 Character Graph Construction

For each NPC/player:

```text
location
known facts
relationship scores
active hooks involving character
motif roles
belief relevance
recent emotional signals
```

### 6.3 Evaluate-Plan-Revise Cycle

Run every 5 turns or via command.

Evaluate:

```text
find coherence issues
```

Plan:

```text
suggest hook merge, context request, retrodiction candidate, motif update
```

Revise:

```text
apply low-risk structural cleanup only
emit high-risk repairs as proposals
```

Example issue:

```text
Mara reacts to Rusk pressure but no event or hook connects Rusk to current report.
```

Possible repair:

```text
create missing communicate_hook with payload rusk_was_cold_or_evasive
or downgrade narration if not admitted
```

---

## 7. v0.4 Pipeline

Target engine pipeline:

```text
1. Build MetaAct
2. Match active EventHooks
3. If no hook match, generate dynamic ActHypothesis
4. Validate support claims
5. Admit proposed effects into AdmittedEvents
6. Apply admitted events through apply_event
7. Update belief layer and retrodiction candidates
8. Generate/decay/merge hooks from ApplyReport
9. Append event graph + character graph updates
10. Periodically run graph diagnosis
11. Render from ApplyReport + presence categories only
12. Archive raw text and structured report
```

---

## 8. Concrete v0.4 Work Items

### Phase A - UPF Event Discipline Port

Files:

```text
metarpg/events.py
metarpg/apply_event.py
metarpg/apply_report.py
```

Tasks:

```text
- Define AdmittedEvent union/classes.
- Define EventApplyOutcome: applied/rejected/deferred.
- Move state mutation out of world.apply_patch into apply_event.
- Add ApplyReport object.
- Add tests mirroring UPF applied/rejected/deferred behavior.
```

### Phase B - STORY2GAME Dynamic Action Contract

Files:

```text
metarpg/action_contract.py
metarpg/proposer.py
metarpg/claims.py
```

Tasks:

```text
- Add explicit schema for LLM/heuristic ActHypothesis v2.
- Add dynamic state-representation update path for safe object tags.
- Add tests for object/property materialization.
```

### Phase C - PLOTTER Graph Layer

Files:

```text
metarpg/plot_graph.py
metarpg/plot_diagnose.py
```

Tasks:

```text
- Build EventGraph from ApplyReport.
- Build CharacterGraph snapshot from WorldState.
- Add diagnostic checks: knowledge leak, character teleport, orphan event, stale hook.
- Add `/plot` debug command.
```

### Phase D - UPF Vendor Notes

Files:

```text
docs/upf_integration_notes.md
```

Tasks:

```text
- Document what was borrowed from UPF.
- Record mapped event types.
- Record what remains vendor-only.
```

---

## 9. Acceptance Tests

### 9.1 UPF-style Event Application

```text
Given AdmittedEvent.travel(player,tavern,guard_post)
When apply_event runs
Then at(player,tavern) is removed
And at(player,guard_post) is added
And ApplyReport says applied
```

### 9.2 Deferred Event

```text
Given add_object("silver_key") with insufficient location support
Then outcome is deferred(reason="missing_context")
And no hard fact is added
And optional request_context event is generated
```

### 9.3 STORY2GAME-style Dynamic Action

Input:

```text
我在矿口找块石头卡住门缝
```

Expected:

```text
- hypothesis has subacts find_object + use_as_tool
- preconditions/support_claims explicit
- loose_stone may be materialized at old_mine_gate
- door-blocking hard fact admitted only if can_block claim passes
```

### 9.4 PLOTTER-style Knowledge Leak Diagnosis

Setup:

```text
Narration/graph suggests Mara reacts to Rusk event before add_knowledge/inform hook.
```

Expected:

```text
plot_diagnose reports knowledge_leak
repair suggestion: downgrade reaction or create missing communication hook candidate
```

### 9.5 Hook + Graph Causality

Input sequence:

```text
old_mine blocked -> force attempt failed -> tell Mara about刚才的情形
```

Expected graph:

```text
old_mine_blocked causes H_guard_mine_report
H_guard_mine_report triggers tell_mara event
tell_mara event adds Mara knowledge / reaction
```

---

## 10. Risk Assessment

### Risk: UPF schema is too RPG-generic

UPF has many useful RPG event types, but MetaRPG needs claim-level admission. Do not let UPF event schema replace claims.

Use UPF for:

```text
event protocol discipline
state-first architecture
apply reports
schema/prompt rigor
```

Do not use UPF as:

```text
the core reasonability matrix
the hook system
the Bayesian belief layer
the PLOTTER graph layer
```

### Risk: STORY2GAME-style dynamic action becomes codegen risk

Do not execute generated code in v0.4. Generate structured claims/effects only.

### Risk: PLOTTER graph diagnosis becomes too abstract

Keep diagnostics concrete and test-driven:

```text
knowledge leak
teleport
orphan event
stale hook
contradiction
```

---

## 11. v0.4 Definition Of Done

v0.4 is done when:

```text
- UPF is vendored and integration notes exist.
- MetaRPG has an UPF-style event application/report layer.
- Dynamic action hypotheses use explicit precondition/effect contract.
- The graph layer records admitted events and character knowledge/location.
- At least 3 graph diagnostics work.
- Existing v0.3.1 hook behavior still passes.
- New tests pass without reducing current 127-test coverage.
```

---

## 12. Conceptual Position

UPF says:

```text
LLM proposes, engine applies.
```

STORY2GAME says:

```text
Actions can be dynamically generated with preconditions and effects.
```

PLOTTER says:

```text
Narrative coherence should be planned and repaired on graphs.
```

MetaRPG v0.4 says:

```text
LLM proposes dynamic action hypotheses.
Claims expose assumptions.
Engine admits consequences as structured events.
Events update state and generate hooks.
Graphs diagnose long-range narrative reasonability.
```

This is the first version where the project has a clear external research alignment without giving up its own core idea:

```text
past events become future-triggering hooks inside a local reasonability engine.
```
