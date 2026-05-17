# MetaRPG Dev v0.5 Plan - Frontier Affordance Expansion

## 0. Version Position

v0.4 establishes the legality layer:

```text
LLM proposes -> claims expose assumptions -> event admission -> apply_event -> ApplyReport -> graph diagnosis
```

v0.5 pushes one layer deeper:

```text
When should the world expand?
How much should it expand?
Which affordances should be generated now?
Which affordances should remain compressed or cold?
```

The central thesis:

```text
Affordance generation is not uniform.
It is frontier-triggered, information-gain-driven, and locally budgeted.
```

Entering a tavern should generate a large local world surface.
Talking to a known NPC inside that tavern should usually generate only a small social/action surface.

---

## 1. Core Problem

Earlier versions still assume that affordance appears in one of two ways:

```text
pre-authored object affordance
LLM-proposed action hypothesis
```

But the real target is more subtle:

```text
The world should know when a player action touches an unexpanded boundary.
At that boundary, the system should expand only the locally relevant world.
```

Example:

```text
Player: 推门进入酒馆
```

This is a high-expansion move because it crosses a scene boundary.
It should materialize:

```text
layout hints
salient NPCs
social temperature
visible objects
current conflicts
exits
ambient information
local rules/taboos
latent hooks
```

Example:

```text
Player: 问玛拉刚才守卫站的事
```

This is a low-expansion move because it operates inside an already-open local scene.
It should mostly materialize:

```text
Mara knowledge state
Mara emotional reaction
topic-specific hooks
possible reply actions
relationship delta
maybe one new thread
```

So v0.5 should not build a bigger generator.
It should build an affordance expansion scheduler.

---

## 2. Conceptual Model

### 2.1 Affordance Definition

In MetaRPG, an affordance is not an object property alone.

Use this definition:

```text
affordance(actor, scene, object, goal, history)
  = probability that an action can be imagined, validated, and executed here
```

For example:

```text
stone -> throwable
```

is too weak.

Better:

```text
player at old_mine_gate
player wants entry
loose_stone plausibly near gate
old gate has a gap
no immediate guard prevents it
=> wedge_gate_with_stone becomes a high-value affordance
```

### 2.2 Frontier

A frontier is a compressed region of the world that is now worth expanding.

Suggested frontier kinds:

```text
scene_boundary
salient_object
unqueried_npc
active_social_tension
unknown_causal_path
latent_hook
unresolved_goal
new_tool_possibility
institutional_rule_boundary
threat_boundary
```

A frontier has:

```text
id
kind
anchor_entity
location
source_event
status: compressed | expanding | expanded | frozen
salience
uncertainty
expected_reuse
risk
budget_hint
created_turn
last_touched_turn
```

### 2.3 Expansion Budget

Each player action receives an expansion budget.

Suggested budget classes:

```text
none       -> only parse/apply known action
small      -> 1-3 affordances
medium     -> 3-8 affordances
large      -> scene entry / major discovery / crisis
emergency  -> contradiction repair / state recovery
```

The budget is not a token budget only.
It is a world mutation budget:

```text
how many new objects may be materialized
how many NPC facts may be added
how many hooks may be created
how many speculative affordances may be cached
how many hard facts may be admitted
```

---

## 3. Expansion Scoring

Candidate affordances should be scored before expansion.

Initial formula:

```text
score =
  player_attention
+ scene_novelty
+ goal_relevance
+ narrative_pressure
+ uncertainty_reduction
+ future_reuse_value
+ hook_connectivity
+ validation_confidence
- verification_cost
- contradiction_risk
- canon_pollution_risk
```

Meaning:

```text
player_attention       -> did the player point at this thing?
scene_novelty          -> is this a newly crossed boundary?
goal_relevance         -> does this help the player's implied goal?
narrative_pressure     -> does current plot/social tension demand it?
uncertainty_reduction  -> will expanding it clarify important unknowns?
future_reuse_value     -> will it become useful future local structure?
hook_connectivity      -> does it connect to existing hooks/events?
validation_confidence  -> can code/claims judge it reliably?
verification_cost      -> how many new assumptions are needed?
contradiction_risk     -> could it violate known canon?
canon_pollution_risk   -> will it add permanent clutter?
```

---

## 4. v0.5 Pipeline

Target runtime pipeline:

```text
1. Parse player input into MetaAct
2. Detect touched frontiers
3. Assign expansion budget
4. Generate candidate affordances only for touched frontiers
5. Score and rank affordances
6. Convert top affordances into ActionHypothesis / support_claims / proposed_effects
7. Validate claims
8. Admit legal effects as AdmittedEvents
9. Apply events through v0.4 apply_event
10. Generate hooks from ApplyReport
11. Update frontier states
12. Record graph edges for expanded affordances
13. Render only admitted local reality
```

Key boundary:

```text
Affordance candidates are not canon.
Only admitted events/facts/hooks become canon.
```

---

## 5. New Components

### 5.1 `metarpg/frontier.py`

Define frontier model and registry.

Core types:

```text
FrontierKind
FrontierStatus
Frontier
FrontierRegistry
```

Minimum API:

```text
create_frontier(kind, anchor, source_event, salience, uncertainty)
touch_frontier(meta_act, world) -> list[Frontier]
mark_expanding(frontier_id)
mark_expanded(frontier_id)
freeze_frontier(frontier_id, reason)
decay_frontiers(turn)
```

### 5.2 `metarpg/affordance.py`

Define affordance candidates.

Core type:

```text
AffordanceCandidate:
  id
  kind
  actor
  anchor
  action_template
  support_claims
  proposed_effects
  source_frontier
  score_breakdown
  persistence: transient | session | canon_candidate
  risk
```

Suggested affordance kinds:

```text
inspect
move_through
talk_about
use_as_tool
force_open
hide
listen
buy_or_trade
ask_for_help
threaten
persuade
report_event
follow_up_hook
```

### 5.3 `metarpg/affordance_expand.py`

Generate candidate affordances from touched frontiers.

This is where LLM can eventually help, but v0.5 should start deterministic/heuristic.

Rules:

```text
scene_boundary -> generate scene surface affordances
salient_object -> generate physical affordances
unqueried_npc -> generate social affordances
active_social_tension -> generate dialogue/conflict affordances
latent_hook -> generate continuation/report affordances
unknown_causal_path -> generate investigate/ask/recall affordances
```

### 5.4 `metarpg/affordance_score.py`

Score candidates using current world state.

Expose:

```text
score_affordance(candidate, world, meta_act, graph) -> ScoreBreakdown
rank_affordances(candidates, budget) -> list[AffordanceCandidate]
```

### 5.5 `metarpg/scene_expand.py`

Special handling for large scene-boundary expansion.

Entering a new location should create a controlled local surface:

```text
scene_summary
visible_entities
visible_objects
ambient_hooks
exits
local_norms
immediate_tensions
```

But these should be tiered:

```text
hard admitted       -> location, exits, explicitly visible anchors
soft visible        -> low-impact objects/NPCs with provenance
latent compressed   -> implied but not materialized until touched
```

### 5.6 `metarpg/debug_affordance.py`

Add debug output for why affordances were or were not generated.

Command target:

```text
/affordance
/frontier
```

Debug report should show:

```text
touched frontiers
budget class
candidate count
top scores
rejected/deferred candidates
canon mutation count
```

---

## 6. Relationship To v0.4

v0.4 provides legality.
v0.5 provides expansion control.

Do not let v0.5 bypass v0.4.

Correct flow:

```text
AffordanceCandidate
  -> ActionHypothesis
  -> support_claims
  -> proposed_effects
  -> AdmittedEvent
  -> apply_event
```

Incorrect flow:

```text
AffordanceCandidate directly mutates WorldState
```

The frontier layer may propose.
The event layer decides.

---

## 7. Example Walkthroughs

### 7.1 Enter Tavern

Input:

```text
推门进入酒馆
```

Detected frontier:

```text
scene_boundary(tavern)
```

Budget:

```text
large
```

Generated surface:

```text
hard:
  player at tavern
  tavern has exit street

soft visible:
  bartender behind counter
  several patrons
  notice board near wall
  back room door

latent:
  a card game tension
  someone may know about guard station
  tavern rumor economy
```

Affordance candidates:

```text
talk_to_bartender
listen_to_room
inspect_notice_board
approach_card_game
ask_about_guard_station
move_to_back_room
```

Only top candidates are surfaced/rendered.
Others remain latent frontier data.

### 7.2 Talk To Mara About Guard Station

Input:

```text
把刚才在守卫站被冷落的事告诉玛拉
```

Detected frontier:

```text
latent_hook(report_guard_station_coldness)
unqueried_npc(Mara)
active_social_tension(player-Rusk)
```

Budget:

```text
small or medium
```

Generated affordances:

```text
report_event_to_mara
ask_mara_for_interpretation
ask_mara_for_help
watch_mara_reaction
```

Admitted effects:

```text
add_knowledge(Mara, rusk_cold_to_player)
relationship_delta(Mara, player, small_empathy?)
open_hook(Mara_may_follow_up_on_Rusk)
```

No new unrelated NPC should appear.
No unrelated tavern object should be materialized.

### 7.3 Search For A Stone At Mine Gate

Input:

```text
我在矿口找块石头卡住门缝
```

Detected frontier:

```text
salient_object(old_mine_gate)
new_tool_possibility(wedge_gate)
```

Budget:

```text
medium
```

Candidate materialization:

```text
loose_stone near old_mine_gate
```

Claims:

```text
plausible_scene_object(loose_stone, old_mine_gate)
has_gap(old_mine_gate)
can_wedge(loose_stone, old_mine_gate)
```

Only if claims pass:

```text
add_object(loose_stone, old_mine_gate)
add_fact(gate_wedged_open, old_mine_gate)
```

If can_wedge fails:

```text
stone exists maybe admitted
wedge effect rejected/deferred
new hook: need_thinner_tool_or_more_force
```

---

## 8. Research And Code References

### 8.1 AGWM - Affordance-Grounded World Models

URL: https://arxiv.org/abs/2605.06841

Why relevant:

```text
It treats affordance space as dynamic and action-dependent.
It models executability through prerequisite dependency structure.
This supports our idea that actions reshape future possibility space.
```

MetaRPG use:

```text
Represent affordance prerequisites as DAG-like dependencies.
Use frontier expansion to decide which part of the affordance DAG to unfold.
```

### 8.2 SayCan - Do As I Can, Not As I Say

URL: https://arxiv.org/abs/2204.01691

Why relevant:

```text
It separates semantic usefulness from executable feasibility.
Language model estimates what is meaningful.
Grounded skill/value functions estimate what is possible.
```

MetaRPG use:

```text
LLM/heuristic scores narrative relevance.
Claim validator/apply_event scores legality and executability.
Final affordance score combines both.
```

### 8.3 AutoGPT+P - Affordance-based Task Planning with LLMs

URL: https://arxiv.org/abs/2402.10778

Why relevant:

```text
It uses affordance-based scene representation for planning.
It treats object-affordance mapping as an intermediate planning substrate.
```

MetaRPG use:

```text
Scene expansion creates local affordance representation.
Planner does not reason over raw prose alone.
```

### 8.4 STORY2GAME

URL: https://arxiv.org/abs/2505.03547

Why relevant:

```text
Dynamic actions are represented through preconditions and effects.
State representation may need to change as new actions are generated.
```

MetaRPG use:

```text
AffordanceCandidate becomes ActionHypothesis.
ActionHypothesis exposes support_claims and proposed_effects.
Safe new object/property materialization is admitted through v0.4 event layer.
```

### 8.5 PLOTTER - Planning Beyond Text

URL: https://arxiv.org/abs/2604.21253

Why relevant:

```text
Narrative coherence is better handled through event and character graphs than raw text.
```

MetaRPG use:

```text
Expanded affordances and admitted events update graph structure.
Graph diagnostics detect bad expansion: knowledge leak, teleport, orphan event, stale frontier.
```

### 8.6 RAP - Reasoning with Language Model is Planning with World Model

URL: https://arxiv.org/abs/2305.14992

Why relevant:

```text
Planning benefits from explicit search over possible future states.
```

MetaRPG use:

```text
Later v0.6 can search over affordance frontiers rather than free-form thoughts.
For v0.5, use the idea lightly: generate several candidates, score, select, and keep deferred branches.
```

### 8.7 Making LLMs into World Models with Precondition and Effect Knowledge

URL: https://aclanthology.org/2025.coling-main.503/

Why relevant:

```text
Preconditions and effects can turn language models into more usable world-model components.
```

MetaRPG use:

```text
Use precondition/effect knowledge as the canonical intermediate form for dynamic affordance.
```

### 8.8 Voyager

GitHub: https://github.com/MineDojo/Voyager
Paper: https://arxiv.org/abs/2305.16291

Why relevant:

```text
Open-ended worlds need exploration curriculum, feedback, and reusable skill memory.
```

MetaRPG use:

```text
Do not generate everything upfront.
Use frontier expansion as a player-driven curriculum.
Store repeatedly validated affordance patterns as reusable local skills/templates.
```

### 8.9 Generative Agents

GitHub: https://github.com/joonspk-research/generative_agents
Paper: https://arxiv.org/abs/2304.03442

Why relevant:

```text
Agent behavior emerges from observation, memory, reflection, and planning.
```

MetaRPG use:

```text
NPC social affordances should depend on memory/reflection-like compressed state, not only current prompt.
```

### 8.10 Viv - Emergent Narrative Engine

Website: https://viv.sifty.studio/

Why relevant:

```text
It emphasizes actions, reactions, story sifting, and causal bookkeeping.
```

MetaRPG use:

```text
Every expanded affordance that becomes real should leave causal bookkeeping.
Story surface should be sifted from causally connected events, not invented at render time.
```

### 8.11 AI-Planning/l2p

GitHub: https://github.com/AI-Planning/l2p

Why relevant:

```text
It explores LLM-driven action model acquisition from natural language.
```

MetaRPG use:

```text
Reference for translating prose action possibilities into predicate/precondition/effect structures.
```

### 8.12 AI-Planning/pddl

GitHub: https://github.com/AI-Planning/pddl

Why relevant:

```text
PDDL is the classic language for predicates, action preconditions, and effects.
```

MetaRPG use:

```text
Do not force all MetaRPG into PDDL.
Use PDDL discipline for small hard-planning islands where symbolic planning is useful.
```

---

## 9. v0.5 Implementation Phases

### Phase A - Frontier Registry

Files:

```text
metarpg/frontier.py
tests/test_v05_frontier.py
```

Tasks:

```text
- Add Frontier dataclass and registry.
- Create scene_boundary frontier when entering unknown/new location.
- Create latent_hook frontier from v0.3.1 event hooks.
- Add decay and status transitions.
```

### Phase B - Expansion Budget

Files:

```text
metarpg/expansion_budget.py
tests/test_v05_budget.py
```

Tasks:

```text
- Classify player actions into none/small/medium/large/emergency.
- Scene entry should produce large budget.
- Known NPC dialogue should produce small/medium budget.
- Contradiction repair should produce emergency budget but not auto-canonize repair.
```

### Phase C - Affordance Candidate Layer

Files:

```text
metarpg/affordance.py
metarpg/affordance_expand.py
metarpg/affordance_score.py
tests/test_v05_affordance.py
```

Tasks:

```text
- Generate candidates from touched frontiers.
- Score candidates with transparent breakdown.
- Rank candidates by budget.
- Convert selected candidates to ActionHypothesis-like contracts.
```

### Phase D - Scene Expansion

Files:

```text
metarpg/scene_expand.py
tests/test_v05_scene_expand.py
```

Tasks:

```text
- Entering a new scene creates controlled local surface.
- Separate hard admitted, soft visible, and latent compressed details.
- Prevent unrelated NPC/object explosion.
```

### Phase E - v0.4 Integration

Files:

```text
metarpg/engine.py
metarpg/apply_event.py
metarpg/plot_graph.py
```

Tasks:

```text
- Hook affordance candidates into existing MetaAct flow.
- Do not bypass claim validation.
- Apply only admitted event effects.
- Record source_frontier on admitted events.
- Add plot diagnostics for stale frontier and over-expansion.
```

### Phase F - Debug Surface

Files:

```text
metarpg/debug_affordance.py
metarpg/cli.py
```

Tasks:

```text
- Add /frontier command.
- Add /affordance command.
- Show why expansion happened and what was rejected/deferred.
```

---

## 10. Acceptance Tests

### 10.1 Tavern Entry Expands Large Surface

Input:

```text
推门进入酒馆
```

Expected:

```text
budget = large
touched frontier includes scene_boundary(tavern)
visible local surface is created
only limited hard facts are admitted
latent affordances exist but do not all become canon
```

### 10.2 Known NPC Conversation Expands Small Surface

Input:

```text
问玛拉关于守卫站的事
```

Expected:

```text
budget = small or medium
touched frontier includes relevant hook/social frontier
no unrelated location/NPC/object materialization
candidate affordances focus on dialogue/report/help/reaction
```

### 10.3 Object Tool Use Is Locally Materialized

Input:

```text
找块石头卡住矿门
```

Expected:

```text
loose_stone may be proposed as soft object
stone existence and wedge effect are separately validated
failed wedge creates deferred hook instead of hallucinated success
```

### 10.4 Frontier Decay

Setup:

```text
latent card_game_tension is not touched for many turns
```

Expected:

```text
frontier salience decays
frontier may become frozen/compressed
it should not keep consuming expansion budget
```

### 10.5 Over-Expansion Diagnostic

Setup:

```text
simple dialogue action creates many unrelated objects/NPCs
```

Expected:

```text
plot_diagnose reports over_expansion
repair suggestion: downgrade materialized entities to latent/frontier-only
```

---

## 11. Metrics

Track these in session logs:

```text
frontiers_touched
expansion_budget_class
candidate_affordances_generated
candidate_affordances_admitted
candidate_affordances_deferred
hard_facts_added
soft_facts_added
latent_frontiers_created
canon_pollution_score
over_expansion_warnings
```

Good behavior:

```text
scene entry has high generated/admitted ratio but bounded hard facts
ordinary dialogue has low materialization count
failed affordance creates useful deferred hook
repeated validated affordances become reusable templates
```

Bad behavior:

```text
small player action spawns many unrelated facts
scene entry creates too many permanent canon details
LLM-proposed affordance bypasses claims
latent frontiers never decay
NPC reacts to non-admitted affordance
```

---

## 12. Definition Of Done

v0.5 is done when:

```text
- Frontier model exists and is persisted in world/session state.
- Scene boundary actions receive larger expansion budgets than ordinary dialogue.
- Affordance candidates are generated, scored, ranked, and converted into claim/effect contracts.
- Expanded candidates still pass through v0.4 event admission.
- Scene entry creates controlled local surface without full-world pre-generation.
- Known NPC dialogue does not create unrelated world objects/NPCs.
- Debug commands explain frontier/budget/affordance decisions.
- At least five v0.5 tests pass while preserving v0.4/v0.3.1 behavior.
```

---

## 13. Conceptual Result

v0.4 says:

```text
No state change without admitted event.
```

v0.5 says:

```text
No affordance expansion without a touched frontier and an explicit budget.
```

This is the step from:

```text
LLM imagines possible actions
```

to:

```text
The world expands locally when player attention touches a meaningful boundary.
```

That is the practical route toward an open world that is not pre-authored, not fully generated upfront, and not free-form hallucination.
