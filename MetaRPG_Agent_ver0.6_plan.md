# MetaRPG Agent v0.6 Plan

## 0. Scope

v0.6 暂时不继续推进 UPF bridge。

本版本只解决 Python 核心体验问题：

```text
玩家不应该面对 code。
玩家应该面对一个能写局部故事的 LLM。
code 应该负责世界状态、上下文整理、事实检查、提交正典。
```

v0.6 的目标不是替换所有旧系统，而是建立一条新的 agentic 主路径：

```text
World Schema
  -> Story Packet
  -> Writer LLM
  -> Translator
  -> Hard Auditor
  -> Soft Auditor LLM
  -> Editor LLM
  -> Targeted Rewrite
  -> Committer
  -> Eval Harness
  -> Teacher Rule Curator
```

旧的 `proposer.py` / deterministic engine 保留为：

```text
- no-LLM fallback
- regression baseline
- simple command fast path
- safety comparison target
```

---

## 1. Core Thesis

The old path made code the interpreter:

```text
player input
-> code parses/proposes hypothesis
-> code assembles patch
-> code validates
-> LLM narrates accepted result
```

This produced stable tests but a raw experience:

```text
one-drink action became ambiguous speech
journal note became talking to Mara
raw event ids leaked into player logs
belief probabilities appeared as player-facing clues
```

v0.6 changes the center of gravity:

```text
LLM writes local story and candidate patch.
Code checks and commits.
Other agents audit and localize repairs.
```

The key distinction:

```text
Do not try to exhaustively classify player behavior.
Constrain the finite set of world consequences.
```

Player behavior is open-ended.
World consequences must be typed, inspectable, and auditable.

---

## 2. Architecture Overview

### 2.1 Layers

```text
Layer 1: World State / World Schema
Layer 2: Writer LLM
Layer 3: Translator Agent
Layer 4: Hard Auditor
Layer 5: Soft Auditor LLM
Layer 6: Editor LLM
Layer 7: Teacher / Rule Curator
```

Strict ownership:

```text
WorldState is code-owned.
Agents never mutate WorldState directly.
Agents only produce drafts, claims, audits, and rewrite tasks.
Committer is the only layer that applies admitted patch effects.
```

### 2.2 Model Roles

Recommended initial assignment:

```text
Writer LLM      = DeepSeek Flash
Translator      = local Qwen3.6, with deterministic scanner support
Soft Auditor    = local Qwen3.6
Editor          = local Qwen3.6
Teacher         = DeepSeek Pro
```

Environment configuration:

```text
Use existing *.env / set.env data.
Do not hardcode API keys or model URLs.
```

---

## 3. Central Data Object: TurnDraft

v0.6 should not make Patch the only central object.

The central object is:

```text
TurnDraft
```

It records the full lifecycle of one turn:

```json
{
  "draft_id": "greyfen_turn_0003",
  "player_input": "一饮而尽",
  "pre_world_ref": "...",
  "story_packet": {},
  "writer_output": {},
  "translated_claims": [],
  "deterministic_scan": {},
  "hard_audit": {},
  "soft_audit": {},
  "editor_tasks": [],
  "rewrite_history": [],
  "final_segments": [],
  "candidate_patch": [],
  "admitted_patch": [],
  "post_world_ref": "...",
  "player_output": "",
  "scorecard": {}
}
```

Every agent call must be logged into the draft.
No failed or repaired segment should disappear without trace.

Suggested file path:

```text
runtime/agentic_runs/{run_id}/turn_{n}.json
```

---

## 4. World Schema

World Schema defines what agents are allowed to talk about and what code can verify.

Initial schema families:

```text
Entity
Location
Object
Fact
Knowledge
Relation
Belief
Hook
Frontier
PatchEffect
NarrativeClaim
VisibilityRule
AuditIssue
RewriteTask
```

### 4.1 Visibility Tiers

Story packets must separate:

```text
visible_to_player
known_to_player
known_to_npc
hidden_truth
belief_debug
recent_events
active_hooks
allowed_reveals
forbidden_mentions
```

This separation is non-negotiable.

If hidden truths are placed in the same bucket as visible facts, Writer and Auditor will leak them.

### 4.2 Patch Effect Kinds

Keep the effect schema small at first:

```text
transient_event
journal_note
observe_reaction
knowledge_transfer
relation_delta
belief_delta
move
add_fact
remove_fact
create_hook
consume_item
acquire_item
risk_flag
reveal
```

Agents may not invent new effect kinds.

Unknown effect kinds are hard failures unless explicitly mapped by schema.

---

## 5. Story Packet Builder

File target:

```text
metarpg/agentic/story_packet.py
```

Responsibilities:

```text
- Build a compact local story packet for one player action.
- Include current location and physically present entities.
- Include player-visible facts and recent player-known events.
- Include NPC-known facts only where relevant.
- Include hidden truths only in a protected section for audit, not Writer narration.
- Include active hooks and recent references.
- Include inventory and local objects.
- Include allowed and forbidden reveal lists.
```

Writer should not receive unrestricted WorldState.

Recommended Writer-facing packet:

```json
{
  "current_scene": {
    "location": "tavern",
    "visible_entities": ["player", "mara"],
    "visible_objects": ["ale_mug", "bar_counter"],
    "atmosphere": "quiet, tense tavern"
  },
  "player_context": {
    "known_facts": ["old_mine_is_sealed"],
    "recent_events": ["player_ordered_ale_from_mara"],
    "inventory_or_handheld": ["ale"]
  },
  "interaction_context": {
    "active_hooks": [],
    "npc_surface_state": {
      "mara": ["cautious", "reserved"]
    }
  },
  "allowed_effect_kinds": ["transient_event", "journal_note", "observe_reaction", "relation_delta", "consume_item"],
  "forbidden": {
    "entities_not_present": ["rusk"],
    "hidden_fact_aliases": ["secret_mine_entrance"],
    "forbidden_narration": ["npc_inner_thought_hidden_fact", "remote_action"]
  }
}
```

Auditor-facing packet may include hidden truth for checking, but it must be clearly labeled.

---

## 6. Writer Agent

File target:

```text
metarpg/agentic/writer_agent.py
```

Model:

```text
DeepSeek Flash
```

Responsibilities:

```text
- Interpret the player action in local context.
- Write segmented player-facing narrative.
- Propose candidate patch effects.
- Declare assumptions explicitly.
- Avoid raw event ids in player text.
- Do not judge final validity.
```

Output schema:

```json
{
  "interpretation": "玩家喝完上一回合得到的麦酒。",
  "segments": [
    {
      "id": "s1",
      "type": "player_action",
      "text": "你仰头喝干杯中的麦酒，苦味在喉间散开。",
      "patch_refs": ["consume_item:ale"],
      "declared_claims": ["player_has_or_holds:ale"]
    },
    {
      "id": "s2",
      "type": "npc_observable_reaction",
      "text": "玛拉瞥了你一眼，又继续擦杯子。",
      "patch_refs": ["observe_reaction:mara:brief_notice"],
      "declared_claims": ["same_location:player:mara"]
    }
  ],
  "candidate_patch": [
    {"kind": "consume_item", "item": "ale"},
    {"kind": "observe_reaction", "target": "mara", "reaction": "brief_notice"}
  ],
  "assumptions": [
    {"claim": "player_has_or_holds:ale", "basis": "recent event player_ordered_ale_from_mara"}
  ]
}
```

Writer constraints:

```text
- Must output segments.
- Every segment must have patch_refs or explain why it is pure sensory/transient text.
- No raw snake_case event ids in segment text.
- No direct NPC inner thoughts unless explicitly allowed.
- No non-present entity action.
```

---

## 7. Translator Agent

File target:

```text
metarpg/agentic/translator_agent.py
```

Model:

```text
local Qwen3.6
```

Translator is not an auditor.

It only answers:

```text
What does this text claim happened?
```

It must not answer:

```text
Is this allowed?
```

### 7.1 Narrative Claim Kinds

Initial closed set:

```text
player_action
player_speech
player_memory_or_journal
npc_speech
npc_observable_action
npc_observable_reaction
npc_inner_state
entity_present_action
object_state
location_state
knowledge_claim
hidden_fact_reference
world_state_change
uncertain_inference
remote_event
raw_debug_exposure
```

Every claim must include:

```json
{
  "segment_id": "s2",
  "kind": "npc_observable_action",
  "subject": "mara",
  "action": "glance",
  "target": "player",
  "evidence_span": "玛拉瞥了你一眼",
  "confidence": 0.92
}
```

Rules:

```text
- Over-extract rather than under-extract.
- Do not merge multiple events into one claim.
- Every claim needs evidence_span.
- If text implies inner knowledge, extract npc_inner_state or knowledge_claim.
- If text mentions hidden fact aliases, extract hidden_fact_reference.
```

### 7.2 Deterministic Scanner

File target:

```text
metarpg/agentic/scanner.py
```

The scanner supports the Translator and catches obvious patterns:

```text
- known entity name scan
- hidden fact alias scan
- snake_case raw event id scan
- inner-thought verb scan: 想到, 意识到, 记得, 知道, 怀疑, 害怕
- remote event cue scan: 与此同时, 远处, 守卫站那边
- unsupported location/entity mentions
```

Scanner findings are not full audits, but they can produce hard audit candidates.

---

## 8. Hard Auditor

File target:

```text
metarpg/agentic/hard_auditor.py
```

Hard Auditor is code-owned.

It takes:

```text
story_packet
writer_output
translated_claims
scanner_findings
candidate_patch
pre_world_state
```

It checks:

```text
1. Entity presence
2. Object existence / possession
3. Location accessibility
4. Knowledge ownership
5. Hidden fact leakage
6. Narrative claim vs candidate patch alignment
7. Patch effect validity
8. Raw debug exposure
9. Hard state change support
10. Contradiction with locked facts
```

### 8.1 Alignment Formula

The core check is:

```text
narrative_claims - supported_by(packet or patch) = unsupported narrative claims
patch_effects - reflected_by(narrative or pure_commit) = ungrounded state changes
```

Both directions matter.

Examples:

```text
story says player drank ale
patch has no consume_item or transient_event
=> mismatch
```

```text
patch adds at(player,guard_post)
story never says movement happened
=> mismatch unless pure_commit explicitly allowed
```

### 8.2 Issue Schema

```json
{
  "severity": "hard_fail",
  "type": "hidden_fact_leak",
  "segment_id": "s3",
  "evidence": "她想起矿井密道",
  "reason": "secret_mine_entrance is hidden and no reveal effect was admitted",
  "repair_instruction": "Remove inner thought and secret entrance. Keep only external observable hesitation."
}
```

Hard failure types:

```text
hidden_fact_leak
absent_entity_action
remote_event_claim
raw_debug_exposure
state_change_without_patch
patch_without_support
locked_fact_contradiction
invalid_effect_kind
```

---

## 9. Soft Auditor Agent

File target:

```text
metarpg/agentic/soft_auditor_agent.py
```

Model:

```text
local Qwen3.6
```

Soft Auditor checks what code cannot easily judge:

```text
- Does the text feel like player-facing RPG prose?
- Does it expose debug concepts?
- Is emotional intensity proportional to patch effects?
- Is the NPC reaction too certain given weak evidence?
- Does the scene repeat prior beats unnaturally?
- Does the narrative imply more than the patch says?
- Is the story vivid but still grounded?
```

Soft Auditor must output structured issues.

It cannot invent new plot.
It cannot commit changes.
It cannot override Hard Auditor.

Soft issue types:

```text
too_mechanical
debug_tone
repetition
overdramatized_reaction
underspecified_feedback
style_drift
weak_player_feedback
```

---

## 10. Editor Agent

File target:

```text
metarpg/agentic/editor_agent.py
```

Model:

```text
local Qwen3.6
```

Editor does not rewrite final story directly.

Editor creates localized rewrite tasks:

```json
{
  "rewrite_tasks": [
    {
      "segment_id": "s3",
      "operation": "replace",
      "severity": "hard_fail",
      "reason": "Hidden fact leak and NPC inner thought.",
      "keep_context_segments": ["s1", "s2"],
      "allowed_patch_refs": ["observe_reaction:mara:brief_notice"],
      "instruction": "Rewrite this segment as an external observable reaction only. Do not mention secret entrance or Mara's inner thoughts."
    }
  ]
}
```

Rules:

```text
- Prefer local repair over full rewrite.
- Preserve passing segments.
- Do not alter admitted patch unless patch itself failed.
- If patch failed, request patch + affected segment rewrite.
- If only prose failed, request narrative-only rewrite.
```

---

## 11. Repair Loop

File target:

```text
metarpg/agentic/repair_loop.py
```

Initial limits:

```text
max_repair_rounds = 2
max_writer_calls_per_turn = 3
```

Repair modes:

```text
Narrative-only repair:
  passing patch retained
  failed segments rewritten

Patch+narrative repair:
  only if candidate_patch failed hard checks
  affected segments rewritten

Fallback:
  if repair still fails, use deterministic safe template
```

No unbounded rewrite loops.

---

## 12. Committer

File target:

```text
metarpg/agentic/committer.py
```

Responsibilities:

```text
- Convert admitted candidate_patch into existing WorldState effects.
- Apply hard state changes.
- Create journal notes.
- Create or update hooks.
- Update relations/beliefs only when admitted.
- Store final player-facing narrative.
```

Only admitted patch effects are committed.

Narrative alone cannot mutate state.

---

## 13. Teacher / Rule Curator

File target:

```text
metarpg/agentic/teacher_agent.py
```

Model:

```text
DeepSeek Pro
```

Teacher is not a hot-path judge.

Teacher is a slow-path rule curator:

```text
After turns, agents may propose recurring or severe issues.
Teacher reviews candidate rule proposals.
Teacher drafts candidate rules and regression tests.
Teacher does not directly patch hard_auditor.py or world_schema.py.
```

### 13.1 Hot Update, Not Bottom-Layer Mutation

Rules may be hot-updated into:

```text
metarpg/agentic/rules/candidate_rules.yaml
metarpg/agentic/rules/session_rules.yaml
runtime/agentic_runs/{run_id}/teacher_proposals.jsonl
```

But they do not automatically enter:

```text
hard_auditor.py
world_schema.py
committer.py
```

Bottom-layer changes require:

```text
- schema validation
- generated regression case
- eval suite pass
- explicit promotion step
```

### 13.2 Escalation Criteria

Only escalate if:

```text
severity=hard_fail
same soft issue appears >= 3 times
editor repair fails
translator/scanner misses repeated pattern
user marks output as bad
```

### 13.3 Teacher Output Schema

```json
{
  "proposal_id": "rule_hidden_inner_thought_v001",
  "problem_pattern": "NPC inner thought exposes hidden fact without reveal patch.",
  "evidence_cases": ["greyfen_004", "greyfen_007"],
  "proposed_rule": {
    "scope": "narrative_claim_audit",
    "rule": "Player-facing narration must not state NPC inner thoughts that contain hidden facts unless an admitted reveal effect exists."
  },
  "schema_change": null,
  "checker_change": {
    "claim_kind": "npc_inner_state",
    "condition": "content references hidden_fact && no reveal effect",
    "severity": "hard_fail"
  },
  "test_cases": [
    {
      "text": "玛拉想起矿井密道，手指一颤。",
      "expected_claims": ["npc_inner_state", "hidden_fact_reference"],
      "expected_result": "fail"
    }
  ],
  "risk": "May over-block literary externalized hesitation.",
  "allowed_alternative": "Allow external observable hesitation without naming hidden fact."
}
```

Teacher may recommend.
Eval Harness and maintainer decide promotion.

---

## 14. Evaluation Framework

File targets:

```text
metarpg/agentic/eval_runner.py
metarpg/agentic/scorecard.py
evals/cases/
evals/runs/
```

Evaluation is the core of agentic development.

If the system cannot score itself, multiple agents will only make failures harder to debug.

### 14.1 Eval Case Schema

```json
{
  "id": "greyfen_003_drink_all",
  "initial_session": "greyfen_default",
  "history": [
    "要了一杯啤酒",
    "耸了耸肩 \"这杯酒真不错\""
  ],
  "player_input": "一饮而尽",
  "expected_interpretation": "玩家喝完上一回合得到的酒",
  "must_include_effect_kinds": ["consume_item"],
  "may_include_effect_kinds": ["transient_event", "observe_reaction"],
  "must_not_include_effect_kinds": ["knowledge_transfer", "move"],
  "forbidden_text": ["拉斯克在角落", "矿井密道", "含糊的话", "player_spoke_unclearly"],
  "must_not_raw_events": true,
  "hidden_facts_must_not_leak": ["secret_mine_entrance"],
  "expected_claim_constraints": [
    "no_npc_inner_state_hidden_fact",
    "no_absent_entity_action"
  ]
}
```

### 14.2 Scorecard Metrics

```text
grounding_score
patch_alignment_score
hidden_leak_count
absent_entity_action_count
raw_debug_exposure_count
unsupported_claim_rate
unregistered_state_change_count
action_understanding_score
rewrite_locality_score
player_experience_score
repair_rounds
token_cost_estimate
latency_ms
```

Hard failures:

```text
hidden_fact_leak
absent_entity_action
remote_event_claim
raw_event_exposure
hard_state_change_without_admitted_patch
final_narrative_contradicts_post_world
```

### 14.3 Minimal v0.6 Acceptance Eval

Use the rough session as the first target:

```text
1. 要了一杯啤酒
2. 耸了耸肩 "这杯酒真不错"
3. 一饮而尽
4. "这附近发生了什么事情么？我是新来的，嘿嘿"
5. 静静地记下了这条信息
```

Acceptance:

```text
- No repeated drink ordering in turn 2.
- Turn 3 is interpreted as drinking/finishing ale.
- Turn 5 is interpreted as journal/internal memory, not NPC speech.
- No belief probabilities in player-facing output.
- No raw event ids in player-facing output.
- Hidden facts do not leak.
- Every final segment has patch_refs or explicit transient justification.
- Failed segments are repaired locally, not full-turn rewritten.
- Final narrative aligns with admitted patch.
```

---

## 15. Proposed File Layout

```text
metarpg/
  agentic/
    __init__.py
    schemas.py
    model_client.py
    story_packet.py
    writer_agent.py
    translator_agent.py
    scanner.py
    hard_auditor.py
    soft_auditor_agent.py
    editor_agent.py
    repair_loop.py
    committer.py
    teacher_agent.py
    eval_runner.py
    scorecard.py
    runner.py
    rules/
      base_rules.yaml
      candidate_rules.yaml

evals/
  cases/
    greyfen_beer_loop.json
    hidden_fact_leak.json
    absent_entity_action.json
    raw_event_exposure.json
  runs/

runtime/
  agentic_runs/
```

---

## 16. Implementation Phases

### Phase A - Data Schemas And Eval Harness

Tasks:

```text
- Add TurnDraft, StoryPacket, Segment, CandidatePatchEffect, NarrativeClaim, AuditIssue, RewriteTask dataclasses.
- Add JSON serialization.
- Add scorecard skeleton.
- Add eval case loader.
- Add mock eval runner that does not call LLM yet.
```

Acceptance:

```text
python -m metarpg.agentic.eval_runner --case evals/cases/greyfen_beer_loop.json --mock
```

produces:

```text
runtime/agentic_runs/{run_id}/turn_*.json
scorecard.json
```

### Phase B - Story Packet Builder

Tasks:

```text
- Convert current WorldState into Writer-facing story packet.
- Add hidden/auditor-only packet layer.
- Suppress hidden beliefs from player-facing packet.
- Include recent events and inventory-like facts.
```

Acceptance:

```text
Story packet for turn 3 includes previous ale event.
Story packet does not expose secret mine entrance as player-visible.
```

### Phase C - Writer Agent

Tasks:

```text
- Add DeepSeek Flash client.
- Add segmented output prompt.
- Validate JSON schema.
- Store raw and parsed outputs in TurnDraft.
```

Acceptance:

```text
Writer outputs segments + candidate_patch for "一饮而尽".
No raw prose-only output accepted.
```

### Phase D - Translator And Scanner

Tasks:

```text
- Add Qwen3.6 translator prompt.
- Add deterministic scanner.
- Require evidence_span on all claims.
- Merge translator claims and scanner findings conservatively.
```

Acceptance:

```text
"玛拉想起矿井密道，手指一颤"
extracts npc_inner_state + hidden_fact_reference + npc_observable_reaction.
```

### Phase E - Hard Auditor

Tasks:

```text
- Implement entity presence check.
- Implement hidden fact leak check.
- Implement raw event exposure check.
- Implement candidate_patch effect kind validation.
- Implement narrative claim vs patch alignment.
```

Acceptance:

```text
Absent Rusk action fails.
Hidden mine entrance leak fails.
"一饮而尽" without consume/transient patch fails alignment.
```

### Phase F - Soft Auditor And Editor

Tasks:

```text
- Add Qwen3.6 Soft Auditor.
- Add Qwen3.6 Editor.
- Editor outputs rewrite tasks, not prose.
- Add local rewrite loop.
```

Acceptance:

```text
Only failing segment is rewritten.
Passing segments remain byte-identical unless explicitly marked for style-only repair.
```

### Phase G - Committer

Tasks:

```text
- Map admitted effects to existing WorldState.
- Add journal notes.
- Add consume_item/acquire_item support if missing.
- Record admitted patch and player output.
```

Acceptance:

```text
Turn 3 consumes or records ale appropriately.
Turn 5 creates journal note instead of NPC speech.
```

### Phase H - Teacher Rule Curator

Tasks:

```text
- Add rule proposal collector.
- Add DeepSeek Pro teacher prompt.
- Store candidate rules in YAML/JSONL.
- Do not auto-modify hard checker code.
```

Acceptance:

```text
Repeated hidden leak issue generates candidate rule + eval test draft.
No bottom-layer code changes occur automatically.
```

---

## 17. Definition Of Done

v0.6 is done when:

```text
- The agentic path can run the 5-turn Greyfen beer loop.
- Writer uses local story packet, not full WorldState.
- Translator extracts narrative claims with evidence spans.
- Hard Auditor catches hidden leaks, absent entity actions, raw event exposure, and patch mismatch.
- Soft Auditor catches debug tone / repetition / weak player feedback.
- Editor localizes rewrite tasks to segment ids.
- Repair loop avoids full-turn rewrite unless unavoidable.
- Committer applies only admitted patch effects.
- Player-facing output contains no raw event ids or belief probabilities.
- Teacher can propose candidate rules without mutating bottom-layer code.
- Eval runner emits TurnDraft artifacts and scorecards.
```

---

## 18. Non-Goals

Not in v0.6:

```text
- UPF integration.
- Full Rust bridge work.
- Full campaign-scale content generation.
- Unlimited open-ended rule learning.
- Automatic hard_auditor.py code mutation by Teacher.
- Replacing all old tests.
```

---

## 19. Final Line

v0.5 proved that MetaRPG can guard canon.

v0.6 must prove that MetaRPG can let LLMs tell a story without losing canon.

The core rule:

```text
Writer imagines.
Translator extracts.
Hard Auditor grounds.
Soft Auditor critiques.
Editor localizes repair.
Teacher curates rules.
Committer alone changes the world.
```
