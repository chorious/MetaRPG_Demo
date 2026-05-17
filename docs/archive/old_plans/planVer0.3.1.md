# MetaRPG Demo v0.3.1 Plan - Subject-Bound Event Hooks

## 0. Why v0.3.1

v0.3 focuses on open Meta-Act hypotheses:

```text
free-form behavior -> support claims -> validation -> selective canonization
```

But the latest session exposed another missing layer:

```text
耸了耸肩，将刚才的情形告诉了玛拉
```

The system treated this as:

```text
ambiguous_social_act / speak_unclearly_to_mara
```

It did not resolve "刚才的情形" into the recent guard-post / old-mine / Rusk sequence.

This is not just memory retrieval. It reveals a deeper mechanic:

```text
Events do not end when they happen.
Important events generate future trigger potentials.
```

v0.3.1 introduces **Subject-Bound Event Hooks**.

---

## 1. Core Thesis

```text
Past event -> active future hook -> player act triggers hook -> patch -> canon/effects
```

Or:

```text
Event Hook = past event compiled into future trigger potential.
```

This is the generated equivalent of a traditional RPG flag/dialogue option.

Traditional RPG:

```text
visited_guard_post = true
rusk_was_cold = true
-> authored dialogue option: [Tell Mara what happened at the guard post]
```

MetaRPG:

```text
guard_post encounter event
-> generated communicate_hook(owner=player, target=mara, payload=guard_post_coldness)
-> player says "将刚才的情形告诉玛拉"
-> hook-trigger patch
```

The important shift:

```text
History is not summarized.
History is compiled into lifecycle-bound triggers.
```

---

## 2. EventHook Model

Add an `EventHook` model.

Suggested fields:

```text
EventHook:
  id: str
  owner: str                    # usually player, but can be NPC later
  source_turn: int
  source_events: list[str]
  hook_type: str                # communicate / confront / investigate / emotion / leverage / return
  trigger_cues: list[str]
  valid_targets: list[str]
  payload_claims: list[Claim]
  proposed_effects: list[ProposedEffect]
  topics: list[str]
  places: list[str]
  participants: list[str]
  priority: float
  ttl: int
  consumed: bool
  decay_policy: str             # consume_once / decay_each_turn / persistent_until_used
```

Debug DSL shape:

```text
@HOOK H7 communicate owner=player ttl=3 target=mara topics=rusk,old_mine
  FROM turn=9,10 source=old_mine_blocked,force_gate_failed
  CUE 刚才|刚刚|情形|告诉|说给|提起|守卫|老矿
  CLAIM player_witnessed(old_mine_blocked)
  CLAIM player_witnessed(rusk_ignored_force_attempt)
  EFFECT add_knowledge(mara,old_mine_access_blocked)
  EFFECT belief_delta(rusk_pressures_mara,+.04)
  EFFECT observe(mara_tenses_at_rusk)
```

---

## 3. Hook Types

Start broad. Later we can compress/merge.

### 3.1 communicate_hook

A past event can be told to someone.

Examples:

```text
tell Mara about Rusk's coldness
tell Rusk what Mara said
tell villager the mine gate is blocked
```

### 3.2 confront_hook

A past event can be used to challenge someone.

```text
confront Rusk about blocking the mine
confront Mara about avoiding the mine topic
```

### 3.3 investigate_hook

A past event opens a follow-up investigation.

```text
return to mine gate
inspect lock/chain
look for another entrance
```

### 3.4 emotion_hook

A past event can be expressed emotionally.

```text
complain about being ignored
show frustration
ask for sympathy
```

### 3.5 leverage_hook

A past event can become social leverage.

```text
use Rusk's behavior to pressure Mara
use Mara's evasiveness to pressure Rusk
```

### 3.6 return_hook

A past location/action creates a natural return affordance.

```text
return to guard_post
return to old_mine_gate
try the gate again
```

---

## 4. Hook Lifecycle

Hooks must not grow without bound.

Minimum lifecycle rules:

```text
- ttl decreases each turn unless persistent
- consumed hooks are hidden from matching
- low-priority hooks expire faster
- similar hooks merge into a stronger hook
- hooks can be promoted if referenced repeatedly
```

Suggested defaults:

```text
communicate_hook: ttl=4, consume_once or decay after trigger
confront_hook: ttl=6, may persist if target unresolved
investigate_hook: ttl=8, persists while location/topic remains unresolved
emotion_hook: ttl=3
leverage_hook: ttl=6
return_hook: ttl=5
```

Hook decay should happen at the beginning or end of each turn.

---

## 5. Hook Generation

After each accepted turn, run:

```text
generate_hooks(turn_record, world)
```

Inputs:

```text
- player input
- accepted canon/transient events
- validation failures
- current location
- physically present entities
- touched entities/topics
- belief changes
```

Important: rejected actions can also generate hooks if they were meaningful.

Example:

```text
go old_mine rejected because sealed
-> hook: communicate old_mine_blocked
-> hook: investigate old_mine_gate
-> hook: confront guard about blocked mine
```

### 5.1 Guard / Mine Hook Example

Sequence:

```text
turn 5: player went to guard_post, met Rusk
turn 7: asked about danger, Rusk was evasive/cold
turn 9: tried to go old_mine, blocked by sealed access
turn 10: tried force gate, failed, Rusk ignored/watched
turn 12: returned to tavern
```

Generated hook:

```text
H_guard_mine_report:
  owner=player
  hook_type=communicate
  valid_targets=[mara]
  trigger_cues=[刚才, 刚刚, 情形, 告诉, 提起, 守卫, 拉斯克, 老矿, 大门]
  payload_claims:
    - player_visited(guard_post)
    - player_met(rusk)
    - rusk_was_cold_or_evasive
    - old_mine_access_blocked
    - player_attempted_force_gate
  proposed_effects:
    - add_knowledge(mara,old_mine_access_blocked)
    - add_knowledge(mara,rusk_was_cold_or_evasive)
    - belief_delta(rusk_pressures_mara,+.04)
    - observe(mara_tenses_at_rusk)
  priority=.85
  ttl=4
```

---

## 6. Hook Matching

Before generic MetaAct proposer, run:

```text
match_active_hooks(metaact, world)
```

Matching signals:

```text
- cue overlap: 刚才 / 刚刚 / 情形 / 那件事 / 告诉 / 提起
- target match: 玛拉 / 拉斯克 / nearby NPC
- topic overlap: 守卫 / 老矿 / 大门 / 危险
- recency
- priority
- owner == player
```

If a hook matches strongly, it should produce an ActHypothesis:

```text
act_kind = trigger_event_hook
subact = communicate_hook_payload
support_claims:
  - hook_active(H_guard_mine_report)
  - same_location(player,mara)
  - can_speak_to(player,mara)
  - player_knows(payload_claims)
intended_effects:
  - add_knowledge(mara,old_mine_access_blocked)
  - add_knowledge(mara,rusk_was_cold_or_evasive)
  - belief_delta(rusk_pressures_mara,+.04)
  - observe(mara_tenses_at_rusk)
  - consume_or_decay_hook(H_guard_mine_report)
```

---

## 7. New Claims For Hooks

Add validators:

```text
hook_active(hook_id)
owner_has_hook(owner,hook_id)
player_knows(claim)
target_valid_for_hook(target,hook_id)
hook_payload_relevant_to_target(hook_id,target)
```

Validation rules:

```text
hook_active: hook exists, not consumed, ttl > 0
owner_has_hook: hook.owner == player
player_knows: source events involved player or fact is in player's knowledge
valid target: target in hook.valid_targets or relevance score above threshold
payload relevance: topic/person overlap with target motifs/beliefs/relations
```

---

## 8. Effects For Hooks

Add effect kinds:

```text
add_knowledge(agent, claim_id_or_fact)
trigger_hook(hook_id,target)
consume_hook(hook_id)
decay_hook(hook_id,amount)
promote_hook(hook_id,amount)
```

Existing `add_knowledge` can be reused if claim payload is normalized to facts.

For v0.3.1, it is acceptable to represent payload claims as compact `Fact` objects:

```text
Fact("old_mine_access_blocked", ())
Fact("rusk_was_cold_or_evasive", ())
Fact("player_attempted_force_gate", ())
```

Later we can make claim IDs richer.

---

## 9. Storage

Add hooks to `WorldState`:

```text
hooks: dict[str, EventHook]
```

Session/debug display should show active hooks:

```text
/hooks
  H_guard_mine_report communicate ttl=3 target=mara priority=.85
  H_old_mine_investigate investigate ttl=6 target=old_mine_gate priority=.70
```

The normal player-facing UI does not need to show hooks unless debug mode is on.

---

## 10. First Required Scenario: "刚才的情形"

Use the latest failure as the first acceptance test.

Script:

```text
准备在酒馆喝一杯麦酒
将麦酒一饮而尽 "这个镇子...有什么我需要注意的么"
前往守卫站
"我想了解一下这附近有没有什么...呃...危险"
前往老矿
尝试用蛮力掰开大门
前往酒馆
耸了耸肩，将刚才的情形告诉了玛拉
```

Expected final turn:

```text
hypothesis_kind == trigger_event_hook
matched_hook == H_guard_mine_report or equivalent
support_claims include:
  hook_active(...)
  same_location(player,mara)
  player_knows(old_mine_access_blocked)
  target_valid_for_hook(mara,...)

canon_delta / effects include some admitted subset:
  add_knowledge(mara,old_mine_access_blocked)
  add_knowledge(mara,rusk_was_cold_or_evasive)
  observe(mara_tenses_at_rusk)
  optional belief_delta(rusk_pressures_mara,+.04)

Narration must mention concrete content:
  - guard post / Rusk / old mine blocked / force attempt failed

Narration must not say only:
  - "含糊地提及刚才的遭遇"
```

---

## 11. Hook Generation Rules For v0.3.1

Start with simple deterministic rules.

### 11.1 Movement to Guard Post

When player arrives at guard_post:

```text
create return_hook guard_post_recent_visit
if rusk present: create communicate_hook met_rusk_at_guard_post
```

### 11.2 Ask/Probe Rusk About Danger/Mine

When player speaks with Rusk about danger/mine/local_news:

```text
create communicate_hook rusk_was_evasive_or_cold
create confront_hook ask_rusk_why_evasive
```

### 11.3 Blocked Old Mine Entry

When move/enter old_mine is rejected due to sealed/inaccessible:

```text
create communicate_hook old_mine_access_blocked
create investigate_hook inspect_old_mine_gate
```

### 11.4 Force Gate Attempt

When player attempts force/open/break door and it fails:

```text
create communicate_hook force_gate_attempt_failed
create emotion_hook frustration_at_mine_gate
create confront_hook ask_rusk_about_gate
```

### 11.5 Merge Rule

If multiple communicate hooks share topics `[rusk, old_mine]` and owner `player`, merge them:

```text
H_guard_mine_report
```

Merge payloads and increase priority.

---

## 12. Important Distinction: Hook vs Memory

This is not RAG.

RAG:

```text
query -> retrieve previous text
```

Hook system:

```text
past event -> future trigger potential
player act -> trigger potential -> patch
```

Hooks are not summaries. They are executable follow-up possibilities.

---

## 13. Bayesian Interpretation

Hooks are a practical form of the Bayesian idea:

```text
past event opens future probability mass
```

Example:

```text
old_mine_blocked
```

opens:

```text
tell_mara_about_block       p=.65
confront_rusk_about_block   p=.35
inspect_gate                p=.70
ignore_and_decay            p=.40
```

Player action selects one path. Unselected hooks decay.

This is subject-bound probability over future actions, not just world-state probability.

---

## 14. Implementation Order

1. Add `EventHook` model and `WorldState.hooks`.
2. Add hook lifecycle tick: decay ttl, consume, merge.
3. Add `hookgen.py`: generate hooks from TurnRecord/canon_delta/validation failures.
4. Add `hookmatch.py`: match active hooks against MetaAct.
5. Modify Engine pipeline:

```text
build_metaact
-> match_active_hooks first
-> if matched, produce hook-trigger hypothesis
-> else normal proposer
-> after turn, generate_hooks
-> tick/merge hooks
```

6. Add claim validators for hook_active/player_knows/target_valid.
7. Add effect handlers for consume_hook/decay_hook/add_knowledge payloads.
8. Add debug command `/hooks`.
9. Add regression test for "刚才的情形".

---

## 15. Acceptance Criteria

v0.3.1 is done when:

```text
- Important past events generate active hooks.
- Hooks are owned by subjects, initially player.
- Hooks have ttl and can decay/consume.
- "刚才的情形" resolves through a communicate hook.
- The final patch carries concrete payload claims from previous events.
- Mara receives at least one concrete knowledge item from the report.
- Narration references the actual guard/mine situation, not vague speech.
- Debug output shows matched hook and admitted effects.
```

---

## 16. Failure Modes To Watch

```text
- Hooks explode without decay/merge.
- Hook payloads become vague summaries instead of claims.
- Hook trigger bypasses claim validation.
- Any "刚才" always picks the most recent hook even if target/topic mismatch.
- NPC receives knowledge about events player did not witness.
- Narrator mentions hook payload as fact before add_knowledge/canon admission.
```

---

## 17. Design Line

```text
Past is not memory.
Past is not summary.
Past is not only canon.
Past is compiled into future-triggering hooks.
```

For v0.3.1:

```text
Event -> Hook -> Trigger -> Patch -> Canon
```
