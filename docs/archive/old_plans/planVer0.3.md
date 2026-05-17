# MetaRPG Demo v0.3 Plan - Open Meta-Act Hypothesis Engine

## 0. Current State

v0.2.1 fixed important admission-control bugs:

```text
- Movement now changes at(player, location)
- sealed old_mine is blocked
- some weak events are downgraded to transient_event
- free-form tavern inputs no longer immediately become unparseable
```

But v0.2.1 is still mostly:

```text
keyword cues -> predefined act_kind -> shallow claims -> patch
```

It is not yet the intended system:

```text
free-form behavior
-> imagined mechanical hypothesis
-> explicit support claims
-> code validation
-> selective canonization
```

v0.3 is the first attempt at that real loop.

---

## 1. v0.3 Goal

Build a minimal **Open Meta-Act Hypothesis Engine**.

The system should accept player behavior that was not preauthored as a command or affordance, then produce a structured hypothesis:

```text
ACT: 我把杯子摔碎，拿碎片吓唬玛拉。

HYPOTHESIS:
  act_kind: composite_physical_social_act
  support_claims:
    - has_or_near(player, ale_mug)
    - fragile(ale_mug)
    - break_creates_shard(ale_mug)
    - can_threaten_with(player, glass_shard)
    - same_location(player, mara)
    - can_speak_to(player, mara)
  intended_effects:
    - transient_event(player_smashed_mug)
    - materialize_object(glass_shard)      [only if claims pass]
    - rel_delta(mara,player,fear,+.12)     [only if social claims pass]
    - rel_delta(mara,player,trust,-.10)
  risks:
    - noise_created
    - rusk_attention_possible
```

Then code decides what survives.

Core boundary:

```text
LLM/proposer can invent mechanics.
Code validates claims.
Patch admits only validated consequences.
Canon stores only admitted consequences.
```

---

## 2. Non-Goals

Do not build a complete physics simulator.
Do not make a huge object ontology.
Do not hand-author every affordance.
Do not let LLM write canon facts directly.
Do not solve all Chinese NLP.
Do not optimize story quality before admission boundaries are correct.

---

## 3. Core Design Shift

v0.2.1 act kinds were still too specific:

```text
order_drink
complain_about_service
ask_about_topic
```

v0.3 should support more abstract hypothesis patterns:

```text
communicative_act
physical_manipulation
object_materialization
use_object_as_tool
threat_or_pressure
deception_or_probe
composite_act
```

These are not final game verbs. They are reasoning containers.

A single player input may produce multiple subacts.

Example:

```text
我把啤酒洒在地图上，看玛拉会不会紧张。
```

Subacts:

```text
1. spill(liquid, target_object)
2. observe_reaction(target_npc)
3. probe_hidden_knowledge(topic=mine/map)
```

---

## 4. New Data Structures

### 4.1 ActHypothesis v2

Extend the hypothesis model to support decomposition.

Suggested shape:

```text
ActHypothesis:
  id: str
  act_kind: str
  confidence: float
  raw_text: str
  target: str
  topic: str
  subacts: list[SubAct]
  support_claims: list[Claim]
  intended_effects: list[ProposedEffect]
  risk_effects: list[ProposedEffect]
  rejected_reason: str | None
```

### 4.2 SubAct

```text
SubAct:
  kind: str
  actor: str
  args: tuple[str, ...]
  claims: list[Claim]
  effects: list[ProposedEffect]
  impact: int
```

Example:

```text
SubAct(kind="break_object", actor="player", args=("ale_mug",))
SubAct(kind="threaten", actor="player", args=("mara", "glass_shard"))
```

### 4.3 Claim

Keep existing `Claim`, but expand claim families.

---

## 5. Claim Families For v0.3

Add enough claims to judge open behavior without a giant ontology.

### 5.1 Existence / Materialization

```text
object_exists(obj)
object_near(actor,obj)
plausible_scene_object(obj,place)
can_materialize(obj,place,impact)
has(actor,obj)
has_or_near(actor,obj)
```

Rules:

```text
- Existing canon object -> ACCEPTED
- Plausible scene object in current place -> INFERRED/PROBABLE
- Implausible object -> UNKNOWN/REJECTED
- Materializing small low-impact prop may be allowed
- Materializing quest-critical object requires explicit scenario support
```

### 5.2 Physical Properties

```text
movable(obj)
fragile(obj)
rigid(obj)
sharp(obj)
flammable(obj)
container(obj)
liquid(obj)
```

Rules should be tiny and type/tag based.

No full physics. Just enough for claims.

### 5.3 Transformation Claims

```text
break_creates(obj,result_obj)
spill_creates(liquid,stain_or_wet_surface)
use_as_tool(obj,tool_function)
can_block(obj,path_or_door)
can_cut(obj,target)
can_throw(actor,obj,target)
```

These are the bridge between imagined mechanics and code validation.

### 5.4 Social / Epistemic Claims

```text
can_threaten(actor,target,means)
can_deceive(actor,target,claim)
can_probe_reaction(actor,target,topic)
topic_sensitive_to(target,topic)
knows_or_may_know(target,topic)
reaction_observable(actor,target)
```

### 5.5 Safety / Canon Claims

```text
not_contradicts_locked_fact(statement)
no_absent_entity_direct_action(target)
impact_within_allowed_bounds(effect)
```

---

## 6. Effect Families For v0.3

Separate effects more strictly.

```text
transient_event(...)       narration/archive only
canon_event(...)           accepted event, not hard fact
add_fact(...)
remove_fact(...)
add_object(...)
remove_object(...)
rel_delta(...)
belief_delta(...)
attention_delta(...)
risk_flag(...)
```

Admission rules:

```text
transient_event:
  may pass with UNKNOWN unless contradicted

canon_event:
  requires no rejected core claims and at least INFERRED support

add_object/materialize:
  requires plausible_scene_object or can_materialize

add_fact/remove_fact:
  requires ACCEPTED core claims

rel_delta:
  requires same_location/can_speak_to or an accepted indirect channel

belief_delta:
  requires relevant observation/probe claim accepted or inferred
```

---

## 7. Object Materialization Rules

This is the first real test of openness.

Examples:

```text
我在矿口找块石头。
```

At `old_mine_gate`:

```text
plausible_scene_object(loose_stone,old_mine_gate) -> INFERRED
can_materialize(loose_stone,old_mine_gate,low_impact) -> ACCEPTED
add_object(loose_stone, old_mine_gate)
add_fact(has(player,loose_stone)) or at(loose_stone,old_mine_gate)
```

At `tavern`:

```text
plausible_scene_object(loose_stone,tavern) -> UNKNOWN/REJECTED
```

But tavern can plausibly contain:

```text
mug, chair, table, bottle, rag, candle, spilled_ale
```

Principle:

```text
The player can query the world for plausible objects.
The world may admit small local props.
The world must not admit quest-solving objects without constraints.
```

---

## 8. Composite Act Decomposition

The proposer should split complex input into subacts.

Example:

```text
我把啤酒洒在地图上，看玛拉会不会紧张。
```

Hypothesis:

```text
SubAct A: spill(player, ale, map)
claims:
  has_or_near(player, ale)
  object_exists(map) or plausible_scene_object(map,tavern)
  liquid(ale)
effects:
  transient_event(player_spilled_ale_on_map)
  add_fact(wet(map)) if map admitted

SubAct B: observe_reaction(player,mara,mine_or_map)
claims:
  same_location(player,mara)
  reaction_observable(player,mara)
  topic_sensitive_to(mara,mine) probable if beliefs include mara_knows_recent_entry
 effects:
  belief_delta(mara_knows_recent_entry,+.05) only if probe claim passes
  rel_delta(mara,player,trust,-.03)
```

If map is not admitted, SubAct A may downgrade to transient_event only. SubAct B may still happen as social observation if Mara is present.

---

## 9. Heuristic Proposer First, LLM Adapter Second

v0.3 can be implemented with a heuristic proposer first, but its output must use the same schema an LLM would use.

Heuristic cues:

```text
break/smash: 摔碎, 打碎, 砸碎, smash, break
spill: 洒, 泼, pour, spill
pick/materialize: 捡, 找, 拿起, pick, find
threaten: 吓唬, 威胁, 逼, threaten
probe: 试探, 看反应, 会不会紧张, probe
pretend/deceive: 假装, 骗, pretend, lie
use_as_tool: 用...来, 拿...去, 卡住, 撬开, cut, wedge
```

v0.3 does not need perfect parsing. It needs explicit claims.

---

## 10. LLM Proposal Contract

When LLM is introduced, it must output only proposals, never canon.

Required structured output:

```json
{
  "act_kind": "composite_act",
  "confidence": 0.74,
  "subacts": [
    {
      "kind": "break_object",
      "actor": "player",
      "args": ["ale_mug"],
      "claims": [
        {"name": "has_or_near", "args": ["player", "ale_mug"]},
        {"name": "fragile", "args": ["ale_mug"]},
        {"name": "break_creates", "args": ["ale_mug", "glass_shard"]}
      ],
      "effects": [
        {"kind": "canon_event", "args": ["player_broke_ale_mug"], "impact": 1},
        {"kind": "add_object", "args": ["glass_shard", "tavern"], "impact": 2}
      ]
    }
  ]
}
```

Then code validates every claim.

---

## 11. Renderer Boundary v0.3

Renderer must receive entity presence categories:

```text
CURRENT_LOCATION
PHYSICALLY_PRESENT
MENTIONED_ONLY
BELIEF_ONLY
MOTIF_RELATED
ADMITTED_EFFECTS
REJECTED_EFFECTS
TRANSIENT_EVENTS
```

Rules:

```text
- Only PHYSICALLY_PRESENT can speak/act in scene.
- MENTIONED_ONLY can be remembered or referenced, not physically staged.
- TRANSIENT_EVENTS can be narrated as attempted/uncertain action.
- Rejected effects must not be narrated as achieved.
```

---

## 12. Required v0.3 Test Inputs

These are the real acceptance tests.

### 12.1 Break Mug + Threaten

```text
我把杯子摔碎，拿碎片吓唬玛拉。
```

Expected:

```text
- Hypothesis decomposes into break_object + threaten
- Claims include fragile(ale_mug), break_creates(ale_mug,glass_shard), same_location(player,mara)
- If player has/near mug, glass_shard may be materialized
- rel_delta fear/trust can apply only if threat claims pass
- No unsupported hard fact enters canon
```

### 12.2 Find Stone At Mine Gate

```text
我在矿口找块石头卡住门缝。
```

Expected:

```text
- At old_mine_gate, loose_stone is plausible
- materialize loose_stone allowed
- wedge/block attempt proposed
- blocked door effect only if door/gap/path claim passes
- Otherwise only stone pickup + attempt transient event
```

### 12.3 Pretend To Know Iven

```text
我假装认识艾文，试探拉斯克的反应。
```

Expected:

```text
- social deception/probe hypothesis
- requires same_location(player,rusk)
- if not same location, no direct Rusk reaction
- if same location, may produce belief_delta about rusk/iven only through observed reaction
```

### 12.4 Spill Beer On Map

```text
我把啤酒洒在地图上，看玛拉会不会紧张。
```

Expected:

```text
- spill + observe_reaction subacts
- map must be existing or plausibly materialized
- Mara reaction only if physically present
- belief update only if topic_sensitive_to(mara,mine) is at least INFERRED/PROBABLE
```

### 12.5 Absent Entity Guard

```text
我向角落里的鲁斯克举杯。
```

If Rusk not present:

```text
- no direct social effect on Rusk
- no narration puts Rusk in the room
- may become intention/thought/transient_event
```

---

## 13. Implementation Order

1. Extend models with `SubAct` and richer `ProposedEffect` if needed.
2. Add new claim validators for object existence/materialization/physical properties.
3. Add effect admission rules for add_object, transient_event, canon_event, rel_delta, belief_delta.
4. Add heuristic open-act proposer for 4-5 target test inputs.
5. Add object registry/tags for minimal Greyfen scene props.
6. Add composite act decomposition.
7. Update renderer context with presence categories.
8. Add v0.3 regression tests.
9. Only then consider LLM proposer adapter.

---

## 14. Minimal Object Tags For Greyfen

Add small type tags, not full ontology.

```text
tavern plausible objects:
  ale_mug: fragile, container, movable
  ale: liquid
  bottle: fragile, container, movable
  chair: movable, rigid
  table: rigid
  candle: flammable, movable
  rag: movable, absorbent
  map: paper, fragile, information_object, optional/probable

old_mine_gate plausible objects:
  loose_stone: rigid, movable, throwable
  debris: rigid
  rope: flexible, movable
  old_door: rigid, blocks_path
  seal_chain: rigid, locked

guard_post plausible objects:
  spear: sharp, weapon
  papers: information_object
  torch: fire_source, movable
```

Important: these are validation supports, not prewritten actions.

---

## 15. What Counts As Success

v0.3 succeeds if the system can take an unpreauthored behavior and produce:

```text
1. A plausible hypothesis
2. Explicit claims exposing hidden assumptions
3. A visible validation result for each claim
4. A patch containing only admitted effects
5. Narration that distinguishes achieved effects from attempted/rejected effects
```

It does not need to always do the most creative thing. It needs to make the boundary inspectable.

---

## 16. Failure Modes To Watch

```text
- LLM/proposer invents object and assembler admits it without plausibility
- rejected effect still appears in narration
- mentioned NPC appears physically
- transient event shown as hard canon
- composite act applies all-or-nothing instead of partial success
- claim validators become a hidden hand-authored affordance table
```

---

## 17. Design Line

v0.2.1 made the engine less wrong.
v0.3 should make the engine qualitatively more open.

```text
The player does not select an affordance.
The player queries possible mechanics.
The proposer imagines the mechanics.
Claims expose the assumptions.
Code admits only the legal consequences.
```
