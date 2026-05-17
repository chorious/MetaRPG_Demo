# MetaRPG Demo v0.2 Core Plan - Meta-Act / Claim Validation

## 0. Why Rewrite v0.2

The previous v0.2 idea was "local affordance matching". That helps, but it is still too close to a preauthored action table:

```text
object/place/role -> predefined affordances -> match player input
```

This does not reach the desired openness. The more radical target is:

```text
Player emits a free-form meta-act.
LLM imagines what this act could mean in the current world.
Code validates the implied claims.
Only validated consequences become canon.
```

Core mantra:

```text
Bold imagination, conservative validation.
```

Or:

```text
LLM may invent acts and implied affordances.
Code may only canonize validated claims.
```

## 1. Diagnosis From v0.1

Recorded failure session:

```text
问问玛拉附近有什么大事
-> parsed target as "ask"
-> REJECT not_same_location(player,ask)

耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"
-> REJECT unparseable_input

"怎么回事，你们酒馆甚至没有酒么！"
-> REJECT unparseable_input
```

This is not merely a parser bug. The system lacks a real semantic compiler.

In v0.2, these inputs should become meta-acts. They do not need to match a command grammar.

## 2. New Core Loop

Replace command parsing as the center with this loop:

```text
Raw player text
  -> MetaAct object
  -> LLM/Heuristic Hypothesis Proposal
  -> Claim Normalization
  -> Code Claim Validation
  -> Patch Assembly from accepted claims/effects
  -> Patch Validation / Forbidden Pattern Check
  -> Selective Canonization
  -> Rendering
```

For v0.2, the "LLM Hypothesis Proposal" may be implemented with deterministic heuristics first, but the interface must be shaped as if an LLM can replace it.

## 3. Key Concept: MetaAct

A MetaAct is the raw player behavior plus local context. It is not yet a game action.

Fields:

```text
raw_text: str
actor: player
turn: int
local_entities: nearby NPCs, objects, places
local_facts: small canon slice
local_beliefs: relevant latent beliefs
speech_fragments: quoted text if any
surface_cues: extracted words/phrases
```

Example:

```text
MetaAct(
  raw_text='耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"',
  actor='player',
  local_entities=['mara','tavern'],
  speech_fragments=['嘿，给我一杯麦芽啤酒'],
  surface_cues=['耸耸肩','要求','酒','麦芽啤酒']
)
```

## 4. Key Concept: Hypothesis Proposal

The proposal layer interprets the meta-act abductively:

```text
What is the player trying to do?
What assumptions would make this action possible?
What consequences would follow if those assumptions are valid?
```

Output shape:

```text
ActHypothesis
  act_kind: str
  confidence: float
  support_claims: list[Claim]
  intended_effects: list[ProposedEffect]
  risks: list[ProposedEffect]
  narration_intent: str
```

Example:

```text
ACT: 给我一杯麦芽啤酒

HYPOTHESIS:
  act_kind = order_drink
  support_claims:
    - same_location(player,mara)
    - role_supports(mara,bartender_service)
    - place_supports(tavern,drink_service)
    - item_plausible(ale,tavern)
  intended_effects:
    - event(player_ordered_ale_from_mara)
    - social_signal(player,mara,ordinary_customer_request)
    - rel_delta(mara,player,trust,+0.01)
  risks:
    - refusal_if(mara_stressed)
```

## 5. Claim Substrate

The system should not need infinite predefined actions. It needs a finite substrate of claims that code can validate.

Minimum v0.2 claim families:

```text
spatial:
  same_location(a,b)
  near(a,b)
  reachable(a,b)

role/service:
  role_supports(entity,service)
  place_supports(place,service)
  item_plausible(item,place)

social:
  can_speak_to(actor,target)
  utterance_targets(raw,target)
  social_tone(raw,tone)

physical placeholder:
  object_exists(obj)
  plausible_scene_object(obj,place)
  movable(obj)

knowledge:
  topic_known_by(target,topic)
  topic_plausible_for_place(topic,place)

canon safety:
  not_contradicts_locked_fact(statement)
```

Do not overbuild. v0.2 needs only enough claims to handle social/tavern inputs and a few object examples.

## 6. Claim Validation Outcomes

Each claim validation returns one of:

```text
ACCEPTED      hard supported by canon/rules
INFERRED      weakly inferred by type/role/place/motif
PROBABLE      plausible but uncertain; allowed for low-impact effects
UNKNOWN       not enough support; can still allow flavor, not hard canon
REJECTED      contradicts canon/rules
```

This is essential. Not every unsupported claim should kill the whole act.

Example:

```text
place_supports(tavern,drink_service) -> INFERRED
role_supports(mara,bartender_service) -> INFERRED
same_location(player,mara) -> ACCEPTED
item_plausible(ale,tavern) -> PROBABLE
```

Therefore an order-drink patch can be assembled.

## 7. Selective Canonization

A proposed act may contain many effects. Only effects whose support claims pass required thresholds become canon.

Impact thresholds:

```text
impact 0 flavor event:
  allow ACCEPTED / INFERRED / PROBABLE / UNKNOWN unless contradicted

impact 1 social texture:
  require no REJECTED core claim

impact 2 belief update / clue pressure:
  require ACCEPTED or INFERRED topic/social claims

impact 3 hard world fact:
  require ACCEPTED claims, or explicit materialization rule

impact 4 retrodiction:
  require full canon validation + forbidden pattern check
```

Thus free-form input can be accepted without letting it freely mutate the world.

## 8. Object Materialization As Validated Hypothesis

The more radical openness comes from allowing player acts to propose objects or affordances that were not predeclared.

Example:

```text
我捡起地上的石头
```

Hypothesis:

```text
act_kind = pick_up_object
support_claims:
  - plausible_scene_object(loose_stone, old_mine_gate)
  - reachable(player, loose_stone)
  - movable(loose_stone)
intended_effects:
  - materialize_object(loose_stone, location=old_mine_gate)
  - has(player, loose_stone)
```

Validation:

```text
old_mine_gate plausibly has loose stones -> INFERRED/PROBABLE
noble_bedroom plausibly has loose stones -> UNKNOWN/REJECTED depending scenario
```

v0.2 does not need a complete object system, but should include this as a design path and maybe one small test.

## 9. Patch Assembly

Patch is no longer directly parsed from text. It is assembled from an accepted hypothesis.

Patch should include debug metadata:

```text
compiler = meta_act
act_kind = order_drink
proposal_confidence = .82
accepted_claims = [...]
rejected_claims = [...]
impact = 1
```

If changing the model is too invasive, represent metadata as effects for now:

```text
EFFECT meta(compiler,meta_act)
EFFECT meta(act_kind,order_drink)
```

## 10. Fallback Behavior

There should be almost no `unparseable_input` for non-empty player behavior.

If no strong hypothesis is found:

```text
act_kind = ambiguous_social_act if nearby NPC exists
```

Patch:

```text
TRY speak(player,mara,raw_utterance)
REQUIRES same_location(player,mara)
EFFECT event(player_spoke_unclearly_to_mara)
EFFECT observe(mara_acknowledged_or_ignored_player)
```

If no nearby NPC exists:

```text
TRY gesture(player,scene,raw_utterance)
EFFECT event(player_made_unclear_gesture)
```

The world can respond lightly even when intent is unclear.

## 11. v0.2 Supported Act Kinds

Implement only a small set of hypothesis act kinds:

```text
ask_about_topic
order_drink
complain_about_service
smalltalk
observe_scene_or_entity
move_to_place
ambiguous_social_act
ambiguous_gesture
```

Optional stretch:

```text
pick_up_plausible_object
use_object_as_tool
```

Important: these are hypothesis labels, not a fixed command grammar. They are outputs of interpretation.

## 12. Examples To Support

### 12.1 Ask Local News

Input:

```text
问问玛拉附近有什么大事
```

Hypothesis:

```text
act_kind = ask_about_topic
support_claims:
  same_location(player,mara)
  can_speak_to(player,mara)
  topic_plausible_for_place(local_news,tavern)
intended_effects:
  event(player_asked_mara_about_local_news)
  observe(mara_response_about_local_news)
  rel_delta(mara,player,trust,+.02)
```

Patch should validate and be accepted.

### 12.2 Order Ale

Input:

```text
耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"
```

Hypothesis:

```text
act_kind = order_drink
support_claims:
  same_location(player,mara)
  role_supports(mara,bartender_service)
  place_supports(tavern,drink_service)
  item_plausible(ale,tavern)
intended_effects:
  event(player_ordered_ale_from_mara)
  social_signal(player,mara,ordinary_customer_request)
  rel_delta(mara,player,trust,+.01)
```

Patch should validate and be accepted.

### 12.3 Complain About No Beer

Input:

```text
"怎么回事，你们酒馆甚至没有酒么！"
```

Hypothesis:

```text
act_kind = complain_about_service
support_claims:
  same_location(player,mara)
  can_speak_to(player,mara)
  place_supports(tavern,drink_service)
intended_effects:
  event(player_complained_to_mara_about_no_service)
  social_signal(player,mara,irritated_customer)
  rel_delta(mara,player,trust,-.03)
  rel_delta(mara,player,fear,+.01)
```

Patch should validate and be accepted.

### 12.4 Ambiguous Social Fallback

Input:

```text
你这里的影子看起来很旧
```

Hypothesis:

```text
act_kind = ambiguous_social_act
support_claims:
  same_location(player,mara)
intended_effects:
  event(player_spoke_unclearly_to_mara)
  observe(mara_acknowledged_or_ignored_player)
```

Patch should validate and be accepted.

### 12.5 Optional Object Materialization

Input at old_mine_gate:

```text
我捡起地上的石头
```

Hypothesis:

```text
act_kind = pick_up_plausible_object
support_claims:
  plausible_scene_object(loose_stone,old_mine_gate)
  reachable(player,loose_stone)
  movable(loose_stone)
intended_effects:
  materialize_object(loose_stone,old_mine_gate)
  add_fact(has(player,loose_stone))
```

Accept only if local place plausibility supports it.

## 13. Implementation Shape

Suggested new modules:

```text
metarpg/metaact.py      # MetaAct extraction from raw text and local slice
metarpg/claims.py       # Claim model + validation outcomes
metarpg/proposer.py     # heuristic v0.2 hypothesis proposer; later LLM adapter
metarpg/assembler.py    # ActHypothesis -> Patch
```

Existing modules remain:

```text
engine.py      # turn loop orchestration
rules.py       # patch-level validation / forbidden patterns
world.py       # canon/matrix state
narrator.py    # rendering only
```

Engine step should become:

```text
meta = build_metaact(text, world)
hypotheses = propose_hypotheses(meta, world)
validated = validate_claims(hypotheses, world)
patch = assemble_best_patch(validated, world)
validate_patch(world, patch)
apply_patch if ok
```

Keep old `parse_input` path as a high-confidence heuristic inside proposer, not as the whole system.

## 14. Heuristic Proposer For v0.2

Before real LLM integration, implement deterministic rules that mimic the desired interface.

Cue examples:

```text
ask_about_topic:
  问, 问问, 打听, 附近, 大事, 最近, 消息, 发生什么

order_drink:
  酒, 啤酒, 麦芽, 来一杯, 买一杯, 喝点, ale, beer

complain_about_service:
  怎么回事, 甚至没有, 没有酒, 抱怨, 不满

observe:
  看看, 环顾, 观察, 打量, 反应

move:
  去, 走到, 前往
```

Target inference:

```text
explicit target if named
else nearest service NPC for social/service acts
else nearby NPC for speech
else scene
```

Topic inference:

```text
大事/最近/消息 -> local_news
矿/矿场/老矿/矿口 -> mine
艾文/伊文/失踪/矿工 -> iven
酒/啤酒/麦芽 -> ale/service
```

## 15. Claim Validation Rules For v0.2

Implement enough validators:

```text
same_location(a,b): ACCEPTED/REJECTED from facts
can_speak_to(a,b): ACCEPTED if same location and b is NPC
role_supports(entity,service): INFERRED from scenario roles
place_supports(place,service): INFERRED from scenario place tags
item_plausible(item,place): PROBABLE/INFERRED from scenario tags
social_tone(raw,tone): INFERRED from cue detection
topic_plausible_for_place(topic,place): INFERRED from scenario topics
plausible_scene_object(obj,place): optional stretch
```

Do not use LLM output as validation. LLM/proposer proposes; code validates.

## 16. Tests To Add

Required tests:

```text
test_metaact_extracts_quoted_speech_and_cues

test_propose_chinese_local_news_question
  input: 问问玛拉附近有什么大事
  expected act_kind: ask_about_topic
  expected claims include same_location(player,mara)

test_order_ale_claims_validate
  input: 耸耸肩，要求买一杯酒 "嘿，给我一杯麦芽啤酒"
  expected accepted patch event player_ordered_ale_from_mara

test_complain_no_beer_claims_validate
  input: "怎么回事，你们酒馆甚至没有酒么！"
  expected accepted patch event player_complained_to_mara_about_no_service

test_unknown_social_input_becomes_ambiguous_social_patch
  input: 你这里的影子看起来很旧
  expected accepted speak/ambiguous event

test_no_unparseable_for_nonempty_nearby_npc
  several arbitrary non-empty Chinese inputs near Mara should produce a patch
```

Optional stretch tests:

```text
test_materialize_loose_stone_at_mine_gate
test_reject_loose_stone_in_implausible_room
```

## 17. Acceptance Criteria

v0.2 is done when:

```text
- The three failure-session inputs produce accepted patches.
- Non-empty social input near an NPC no longer returns unparseable_input.
- Debug output shows hypothesis, support claims, validation outcomes, assembled patch.
- Rejected actions fail because of claim/patch validation, not parser ignorance.
- Hard canon is still protected: unsupported high-impact effects are not canonized.
```

The key success is not perfect natural language understanding. The key success is this boundary:

```text
The system can imagine an interpretation, then legally admit only what survives validation.
```

## 18. Future LLM Adapter

When replacing heuristic proposer with LLM, require structured output:

```text
{
  "act_kind": "order_drink",
  "confidence": 0.82,
  "support_claims": [
    {"name":"same_location", "args":["player","mara"]},
    {"name":"place_supports", "args":["tavern","drink_service"]}
  ],
  "intended_effects": [
    {"kind":"event", "args":["player_ordered_ale_from_mara"]}
  ],
  "impact": 1
}
```

Never allow LLM to directly write canon. It only writes claims and proposed effects.

## 19. Design Mantra

```text
The player emits behavior, not commands.
The LLM/proposer invents possible mechanics.
Claims expose the hidden assumptions.
Code validates the assumptions.
Patch assembles only admitted consequences.
Canon records only what survived.
```
