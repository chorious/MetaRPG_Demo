# MetaRPG Agent v0.6.1 Review

## Summary

v0.6 的 agentic 方向是对的。

这次 `runtime/agentic_runs/smoke_06e4986a/` 说明：

```text
Writer 已经能明显改善旧 engine 的 raw 行为解释。
Soft Auditor 已经能抓到部分体验问题。
但 Hard Auditor、状态连续性、scorecard、repair loop 还没有形成可信闭环。
```

最重要的修正是：

```text
Hard Auditor 不应该禁止合理氛围补全。
Hard Auditor 应该禁止未登记的剧情后果。
```

也就是：

```text
ambient detail can float.
story consequence must dock to patch.
```

---

## 1. Smoke Run Observations

Run:

```text
runtime/agentic_runs/smoke_06e4986a/
```

Files:

```text
turn_001.json
turn_003.json
turn_004.json
turn_005.json
scorecard_001.json
scorecard_003.json
scorecard_004.json
scorecard_005.json
```

Immediate issue:

```text
turn_002 / scorecard_002 missing
```

This is either:

```text
- runner skipped a turn
- file numbering bug
- failed turn was not persisted
```

Any of these breaks state-continuity evaluation.

---

## 2. Positive Signal

The Writer no longer makes the old v0.5 mistake:

```text
一饮而尽 -> player_spoke_unclearly_to_mara
```

Instead it interpreted:

```text
一饮而尽 -> player drinks / finishes ale
```

This is a strong sign that LLM-first interpretation is the right direction.

The Writer also produced segmented text, candidate patches, assumptions, and risk notes.
This is the correct artifact shape for v0.6.

---

## 3. Main Failure: Evaluation Is Not Trustworthy Yet

All scorecards report:

```json
{
  "grounding_score": 1.0,
  "patch_alignment_score": 1.0,
  "player_experience_score": 1.0,
  "hard_failures": [],
  "soft_issues": []
}
```

But `turn_004.json` and `turn_005.json` contain:

```json
"soft_audit": {
  "passed": false,
  "issues": [...]
}
```

So scorecard is not absorbing Soft Auditor output.

Also:

```text
player_output is empty in turn drafts
```

This means player-facing checks such as forbidden text, raw event exposure, and experience score are not being evaluated against the actual final output.

### Required Fix

Scorecard must ingest:

```text
hard_audit.issues
soft_audit.issues
editor_tasks
rewrite_history
final_segments
player_output
admitted_patch
```

If:

```text
soft_audit.passed=false
```

then:

```text
player_experience_score < 1.0
soft_issues non-empty
notes include issue summaries
```

If:

```text
player_output empty
```

then:

```text
player_experience_score = 0.0
notes include missing_player_output
```

---

## 4. Main Design Correction: Hard vs Medium vs Soft

The first instinct was to hard-fail everything not listed in `story_packet.visible_entities` or `visible_objects`.
That is too strict and would recreate the old code-dominant feeling.

The better distinction:

```text
Hard: unsupported story consequence
Medium: risky concrete assumption
Soft: tone, fit, continuity, texture
```

### 4.1 Hard Auditor Should Catch

```text
- Named absent entity acts / speaks / reacts.
- NPC speech that is not represented by patch.
- New concrete interaction offer not represented by patch.
- Hidden fact leak.
- Remote event presented as directly perceived.
- Raw event/debug ID in player-facing text.
- Hard state change in narrative without patch.
- Patch effect with no narrative support, unless pure_commit allowed.
- Invalid effect kind.
- Locked fact contradiction.
```

### 4.2 Medium Auditor Should Catch

```text
- Unregistered concrete prop used for a meaningful action.
- Ambient entities becoming too specific.
- Implied new affordance not in patch.
- Specific item usage based only on assumption.
- Knowledge transfer using vague/untyped content.
```

Medium issues may trigger repair, but they do not always hard-fail the turn.

### 4.3 Soft Auditor Should Catch

```text
- Tone drift.
- Genre mismatch.
- Repetition.
- Overdramatized reaction.
- Weak player feedback.
- Debug-like phrasing.
- Scene prose disconnected from player action.
```

Soft issues should affect player experience score and may trigger localized rewrite.

---

## 5. Reclassifying The Smoke Issues

### 5.1 Turn 004: Unnamed Tavern Guests

Text:

```text
远处三两桌低声交谈的客人偶尔瞥你一眼
```

Initial criticism treated this as hard failure because `visible_entities` only listed:

```text
player, mara
```

That was too strict.

In a tavern, unnamed guests are reasonable ambient population.

Correct classification:

```text
PASS as ambient detail
```

Conditions:

```text
- They remain unnamed.
- They do not produce specific plot knowledge.
- They do not become active quest/NPC entities.
- They do not create relation/knowledge/combat effects.
- They are not used as witnesses unless patch records it.
```

Recommended Translator kind:

```text
ambient_entity_action
subject=unnamed_guests
scope=background
```

Hard Auditor should allow this claim class under scene-appropriate conditions.

### 5.2 Turn 005: Notebook And Ink

Text:

```text
你从怀中取出随身携带的笔记本，蘸了蘸墨水
```

This is not automatically hard-invalid.
An adventurer carrying notes can be plausible.

But it is too specific for the provided packet:

```text
inventory_or_handheld=[]
visible_objects=[]
```

And it clashes with the previous casual tone.

Correct classification:

```text
medium_issue or soft_issue
```

Suggested issue:

```text
type: unregistered_concrete_prop
severity: medium_issue
segment_id: s1
```

Repair preference:

```text
Use lower-commitment prose:
"你把这句话默默记在心里。"
```

Only hard-fail if:

```text
- notebook/ink becomes a persistent object
- patch adds notebook/ink
- later logic relies on notebook/ink
- world explicitly denies such tools
```

### 5.3 Turn 003: "再来一杯？"

Text:

```text
“好酒量。”她随口赞了一声，但语气里带着一丝试探，“再来一杯？”
```

This is the real alignment issue.

It introduces:

```text
npc_speech
social offer
new interaction opportunity
potential refill affordance
```

But candidate patch only contains:

```json
[
  {"kind": "transient_event", "args": {"description": "player_drank"}},
  {"kind": "observe_reaction", "args": {"reaction": "mild_interest"}}
]
```

Correct classification:

```text
hard_fail or medium-high issue
```

Recommended hard issue:

```json
{
  "severity": "hard_fail",
  "type": "npc_speech_without_patch_support",
  "segment_id": "s3",
  "evidence": "“好酒量。” ... “再来一杯？”",
  "reason": "NPC speech and refill offer create a concrete interaction opportunity not represented in candidate_patch.",
  "repair_instruction": "Either add npc_speech/offer_refill/create_affordance patch effects, or rewrite the segment as a silent observable reaction."
}
```

---

## 6. Story Packet Problems

### 6.1 Missing State Continuity

Turn 003 should know that the player acquired ale earlier.

But story packet shows:

```json
"recent_events": [],
"inventory_or_handheld": [],
"visible_objects": []
```

So Writer could only assume ale existed.

Result:

```text
Writer used transient_event instead of consume_item.
```

### Required Fix

Committer must update a player context source consumed by next StoryPacket:

```text
acquire_item:ale -> player_context.inventory_or_handheld includes ale
consume_item:ale -> remove ale or mark consumed
knowledge_transfer -> known_facts includes transferred fact
journal_note -> player notes include fact/note
create_hook -> active_hooks includes hook
```

StoryPacketBuilder must include:

```text
recent admitted events
inventory_or_handheld
player knowledge
journal notes
active hooks
```

### 6.2 Writer-Facing Packet Leaks Debug Numbers

Writer-facing packet includes:

```json
"visible_mood": ["trust=+0.18", "curiosity=+0.35"]
```

This causes Writer to reason in system terms.

Required change:

Writer-facing:

```text
reserved
mildly curious
cautious
```

Auditor/debug-only:

```text
trust=+0.18
curiosity=+0.35
```

---

## 7. Hard Auditor Rule Updates

### 7.1 Add Claim Classes

Translator should distinguish:

```text
ambient_entity_action
named_entity_action
npc_speech
npc_offer
prop_usage
unregistered_prop_usage
concrete_affordance_creation
```

This prevents two bad extremes:

```text
unnamed tavern guests hard-fail
NPC offer passes as vague observe_reaction
```

### 7.2 New Alignment Rules

Hard:

```text
npc_speech claim requires one of:
- npc_speech patch
- knowledge_transfer patch
- reveal patch
- transient_event explicitly describing speech
```

Hard or medium-high:

```text
npc_offer / concrete_affordance_creation requires:
- offer_* patch
- create_affordance patch
- transient_event explicitly recording the offer as non-committed
```

Medium:

```text
prop_usage of unregistered object requires:
- object in inventory_or_handheld
- object in visible_objects
- object is scene_plausible_ambient_prop
- or treat as low-commitment narration only
```

Pass:

```text
ambient_entity_action allowed if:
- unnamed
- background only
- scene supports ambient population
- no patch-relevant consequence
```

---

## 8. Soft Auditor And Editor Integration

Soft Auditor worked better than the scorecard suggests.

Examples:

```text
Turn 004: scene prose disconnected from previous drink action.
Turn 005: notebook/ink tone drift and weak feedback.
```

But:

```text
editor_tasks=[]
repair_rounds=0
scorecard.soft_issues=[]
```

So soft issues are currently dead-end diagnostics.

### Required Fix

If soft issues exist:

```text
run Editor
create localized rewrite tasks
perform narrative-only rewrite unless configured as report-only
record rewrite_history
update final_segments
update player_output
rescore
```

If repair disabled:

```text
scorecard must still record soft_issues and reduce player_experience_score
```

---

## 9. Scorecard Updates

Current scorecard is too optimistic.

Add:

```text
soft_issue_count
medium_issue_count
hard_issue_count
missing_player_output
missing_turn_sequence
state_continuity_score
packet_support_score
```

Suggested scoring:

```text
hard failure -> acceptable=false
medium issue -> player_experience_score capped at 0.75
soft issue -> player_experience_score capped at 0.85 unless repaired
missing player_output -> player_experience_score=0
missing turn in sequence -> run-level failure
```

`is_acceptable()` should stay hard-rule focused, but scorecard must not hide medium/soft issues.

---

## 10. v0.6.1 Implementation Order

1. Fix turn sequence persistence.
   ```text
   Ensure turn_001..turn_005 all exist or failed turns are written with error status.
   ```

2. Fix `player_output`.
   ```text
   Always join final_segments into player_output before scoring and saving.
   ```

3. Feed committed state into next StoryPacket.
   ```text
   acquire_item / consume_item / knowledge_transfer / journal_note must affect next packet.
   ```

4. Remove debug numbers from Writer-facing packet.
   ```text
   Translate relation values into qualitative surface descriptions.
   ```

5. Add claim classes for ambient, speech, offer, prop usage.

6. Update Hard Auditor alignment rules.
   ```text
   Allow ambient details.
   Require patch support for NPC speech/offers/hard consequences.
   ```

7. Add medium issues.
   ```text
   Do not hard-fail plausible but unsupported props.
   Track and optionally repair them.
   ```

8. Wire Soft Auditor into scorecard and Editor.

9. Add regression evals:
   ```text
   unnamed tavern guests should pass
   notebook/ink should medium issue
   npc "再来一杯？" without patch should fail
   ```

---

## 11. Concrete Regression Cases

### Case A - Ambient Guests Pass

Input text:

```text
远处三两桌低声交谈的客人偶尔瞥你一眼。
```

Expected:

```text
claim_kind=ambient_entity_action
hard_audit=pass
no entity added to WorldState
no relation/knowledge effects
```

### Case B - Notebook Is Medium

Input text:

```text
你从怀中取出笔记本，蘸墨写下这条消息。
```

Packet:

```text
inventory_or_handheld=[]
visible_objects=[]
```

Expected:

```text
medium_issue=unregistered_concrete_prop
not hard_fail unless notebook is committed as object
repair suggests lower-commitment memory/journal phrasing
```

### Case C - NPC Offer Needs Patch

Input text:

```text
玛拉说：“再来一杯？”
```

Patch:

```json
[
  {"kind": "observe_reaction", "args": {"target": "mara", "reaction": "mild_interest"}}
]
```

Expected:

```text
hard_fail=npc_speech_without_patch_support or npc_offer_without_patch_support
repair requires adding npc_speech/offer_refill patch or rewriting speech away
```

---

## 12. Revised Review Line

The smoke run should not push us toward a stricter packet whitelist.

It should push us toward a better distinction:

```text
Ambient texture may be loosely inferred.
Concrete consequences must be explicitly docked to patch.
```

v0.6.1 should make the auditors less naive, not merely harsher.

The target is:

```text
Writer stays imaginative.
Hard Auditor catches real consequence drift.
Medium layer catches risky assumptions.
Soft Auditor preserves feel.
Editor repairs locally.
Scorecard tells the truth.
```
