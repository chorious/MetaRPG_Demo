# MetaRPG Architecture Reorganization Plan

## 0. Purpose

The project has reached a point where idea growth is faster than structural clarity.

This plan is not about removing work.
It is about separating tracks so each part has a clear role:

```text
legacy deterministic core -> stable baseline
agentic v0.6 pipeline     -> main current experiment
UPF bridge                -> paused integration track
runtime artifacts         -> evidence, not architecture
docs                      -> versioned design memory
```

The immediate goal is to make the project navigable again and prevent new features from landing in the wrong layer.

---

## 1. Current Problem

The repo currently mixes several active concepts at the same level:

```text
v0.1-v0.5 deterministic engine
v0.5.1 UPF bridge
v0.6 agentic LLM pipeline
eval experiments
runtime logs
plans/reviews/prompt references
```

This creates three failure modes:

```text
1. Every new idea feels like it must touch every file.
2. Old deterministic logic keeps competing with new agentic logic.
3. Runtime artifacts are treated like architecture instead of evidence.
```

The result is conceptual fragmentation.

---

## 2. Strategic Decision

For the next development phase:

```text
Main track: v0.6 agentic Python pipeline
Baseline: legacy deterministic engine
Paused: UPF bridge
Primary eval: Greyfen 5-turn beer loop
```

No new UPF work until the Python agentic loop is stable.

No new `proposer.py` behavior categories unless needed for legacy regression.

No Teacher-driven bottom-layer rule mutation.

---

## 3. Target Repository Shape

Recommended eventual layout:

```text
metarpg/
  core/
    models.py
    world.py
    rules.py
    claims.py
    hooks.py
    hookmatch.py
    hookgen.py
    frontier.py
    affordance.py
    retrodict.py
    plot_graph.py
    plot_diagnose.py

  legacy/
    engine.py
    proposer.py
    assembler.py
    metaact.py
    narrator.py
    cli.py
    session_logger.py

  agentic/
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

  bridge/
    bridge.py
    bridge_protocol.py
    bridge_session.py
    export_snapshot.py

  scenarios/
    greyfen.py

docs/
  architecture/
  plans/
  reviews/
  prompts/
  archive/

evals/
  cases/
  rubrics/
  runs/

runtime/
  sessions/
  bridge_sessions/
  agentic_runs/

vendor/
  Unlimited_possibilies_framework/
```

Important:

```text
This does not have to be moved all at once.
Start by documenting the boundaries, then move files only when imports are stable.
```

---

## 4. Track Definitions

### 4.1 Core

Core is code-owned world logic.

It contains:

```text
WorldState
Fact / Knowledge / Relation / Belief
rules
claims
hooks
frontiers
retrodiction
plot diagnostics
```

Core must not know about:

```text
LLM prompts
Writer / Auditor agents
UPF
runtime output format
```

Core should expose stable functions that both legacy and agentic paths can use.

### 4.2 Legacy

Legacy is the deterministic v0.1-v0.5 engine.

It contains:

```text
parser
meta-act
proposer
assembler
old turn loop
CLI
session markdown logger
```

Role:

```text
stable baseline
fallback mode
regression comparison
```

Do not keep expanding it as the main experience path.

### 4.3 Agentic

Agentic is the v0.6 main experimental path.

It contains:

```text
StoryPacketBuilder
Writer
Translator
Scanner
Hard Auditor
Soft Auditor
Editor
Repair loop
Committer
Teacher
Eval harness
```

Role:

```text
make the player face story, not code
let LLM interpret/write
let code ground/commit
```

### 4.4 Bridge

Bridge is paused.

It contains:

```text
Python JSON bridge
session adapter
UPF protocol
snapshot export
```

Role:

```text
future playable shell integration
```

Rule:

```text
Do not resume bridge work until agentic Python loop passes primary eval.
```

### 4.5 Docs

Docs are design memory.

They should be separated by type:

```text
plans     -> intended work
reviews   -> critique of current state
prompts   -> prompt references and rubrics
architecture -> stable boundary/interface docs
archive   -> old plans kept for traceability
```

---

## 5. Stable Interfaces

The reorg should be driven by interfaces, not file moves.

v0.6 needs five stable interfaces.

### 5.1 WorldState -> StoryPacket

Purpose:

```text
Turn code-owned world state into LLM-usable local context.
```

Must separate:

```text
visible_to_player
known_to_player
known_to_npc
hidden_truth
recent_events
active_hooks
allowed_reveals
forbidden_mentions
```

Writer-facing packet must not expose:

```text
belief probabilities
debug IDs
hidden facts
raw internal event names
```

### 5.2 WriterOutput -> NarrativeClaims

Purpose:

```text
Translate natural language segments into structured claims.
```

Translator must:

```text
extract claims
attach evidence_span
avoid judging validity
over-extract rather than under-extract
```

### 5.3 NarrativeClaims + CandidatePatch -> AuditReport

Purpose:

```text
Check whether story claims and patch effects align with world rules.
```

Hard Auditor checks:

```text
hidden leaks
absent named entity action
npc speech without patch support
hard state change without patch
invalid effect kind
locked fact contradiction
raw debug exposure
```

Medium layer checks:

```text
unregistered concrete props
ambient entities becoming too specific
implied affordance not in patch
```

Soft Auditor checks:

```text
tone
continuity
debug-like phrasing
weak feedback
overdramatization
```

### 5.4 AuditReport -> RewriteTasks

Purpose:

```text
Convert issues into local repair instructions.
```

Editor must:

```text
preserve passing segments
target failing segment ids
avoid full-turn rewrite unless required
not invent new plot
```

### 5.5 AdmittedPatch -> WorldState

Purpose:

```text
Commit only audited consequences.
```

Committer must update:

```text
facts
knowledge
relations
beliefs
hooks
inventory/context notes
recent events
journal notes
```

Narrative alone cannot mutate state.

---

## 6. Documentation Standard

Root should stop accumulating plan/review/prompt files.

Allowed root files:

```text
README.md
PROJECT_STATUS.md
ARCHITECTURE_REORG_PLAN.md
pyproject.toml
requirements.txt
set.env
```

All other planning and review material should live under `docs/`.

### 6.1 Docs Layout

```text
docs/
  architecture/
    ARCHITECTURE_REORG_PLAN.md
    v0.6_interfaces.md
    artifact_schema.md

  plans/
    MetaRPG_Agent_ver0.6_plan.md

  reviews/
    reviewVer0.5.2.md
    reviewVer0.6.1.md

  prompts/
    MetaRPG_Agent_story_prompt_reference.md

  archive/
    old_plans/
      planVer0.1.md
      planVer0.2.md
      planVer0.3.md
      planVer0.3.1.md
      planVer0.4.md
      planVer0.5.md
      planVer0.5.1-playable-upf-bridge.md
    old_reviews/
      review_v0.2.1.md
```

### 6.2 Naming Rules

Plans:

```text
docs/plans/planVerX.Y[-topic].md
docs/plans/MetaRPG_Agent_verX.Y_plan.md
```

Reviews:

```text
docs/reviews/reviewVerX.Y.md
```

Architecture:

```text
docs/architecture/<stable_interface_or_process>.md
```

Prompts:

```text
docs/prompts/<agent_or_eval>_prompt_reference.md
```

Archive:

```text
docs/archive/old_plans/
docs/archive/old_reviews/
```

### 6.3 Root Cleanup Rule

When a new plan/review/prompt is created:

```text
create it directly in docs/<category>/
```

Do not create it in root and move later.

Existing root docs should be moved in a docs-only cleanup commit with no behavior changes.

---

## 7. Runtime Artifact Standard

Every agentic run should produce:

```text
runtime/agentic_runs/{run_id}/
  run_manifest.json
  turn_001.json
  scorecard_001.json
  turn_002.json
  scorecard_002.json
  ...
  events.jsonl
  errors.jsonl
  summary.md
```

### 7.1 run_manifest.json

Required fields:

```json
{
  "run_id": "smoke_xxxxxxxx",
  "case_id": "greyfen_beer_loop",
  "created_at": "...",
  "mode": "mock | live",
  "models": {
    "writer": "deepseek-flash",
    "translator": "qwen3.6-local",
    "soft_auditor": "qwen3.6-local",
    "editor": "qwen3.6-local",
    "teacher": "deepseek-pro"
  },
  "turns_expected": 5,
  "turns_written": 5,
  "missing_turns": [],
  "hard_failures": [],
  "medium_issues": [],
  "soft_issues": [],
  "acceptable": true
}
```

### 7.2 Turn Draft

Each `turn_NNN.json` must include:

```text
player_input
story_packet
writer_output
translated_claims
scanner_findings
hard_audit
soft_audit
editor_tasks
rewrite_history
candidate_patch
admitted_patch
final_segments
player_output
pre_world_ref
post_world_ref
```

If a turn fails, write:

```text
turn_NNN_error.json
```

The error turn must include:

```text
draft_id
player_input
story_packet if available
error_stage
error_type
error_message
error_traceback
raw_writer_output / raw_translator_output / raw_auditor_output if available
scorecard
```

Do not allow a failed turn to disappear silently.

### 7.3 Scorecard

Each scorecard must include:

```text
hard_issue_count
medium_issue_count
soft_issue_count
player_experience_score
state_continuity_score
packet_support_score
missing_player_output
repair_rounds
acceptable
```

### 7.4 events.jsonl

Each run should have a chronological machine-readable event stream.

One JSON object per line:

```json
{
  "ts": "2026-05-18T03:37:04+08:00",
  "run_id": "play_e3c3006d",
  "turn": 2,
  "stage": "writer",
  "event": "start",
  "message": "Writer call started"
}
```

Recommended event names:

```text
run_start
turn_start
story_packet_built
writer_start
writer_success
writer_failure
translator_start
translator_success
translator_failure
scanner_success
hard_audit_success
soft_audit_success
editor_success
commit_success
scorecard_written
turn_written
turn_error_written
run_end
```

### 7.5 errors.jsonl

Any exception should also be appended to:

```text
errors.jsonl
```

Required fields:

```json
{
  "ts": "...",
  "run_id": "play_e3c3006d",
  "turn": 2,
  "stage": "writer",
  "error_type": "WriterOutputError",
  "error_message": "Writer returned invalid JSON...",
  "traceback": "...",
  "artifact": "turn_002_error.json"
}
```

If raw model output exists, store it in the turn error artifact, not directly in `errors.jsonl`, to keep the error stream compact.

### 7.6 summary.md

Each run should end with a short human-readable summary:

```text
# Run play_e3c3006d

Case: interactive
Turns attempted: 2
Turns completed: 1
Failed at: turn 2 / writer

## Failures
- turn_002 writer_failure: invalid JSON

## Scores
- turn_001: experience 1.00 / grounding 1.00
```

### 7.7 Runtime Separation

Runtime output should stay under:

```text
runtime/
```

Never store runtime logs under `docs/`.

Docs describe design.
Runtime artifacts record evidence.

---

## 8. Primary Eval

The primary eval is:

```text
Greyfen 5-turn beer loop
```

Turns:

```text
1. 要了一杯啤酒
2. 耸了耸肩 "这杯酒真不错"
3. 一饮而尽
4. "这附近发生了什么事情么？我是新来的，嘿嘿"
5. 静静地记下了这条信息
```

Acceptance:

```text
- turn files are continuous
- player_output is non-empty
- no raw event ids in player output
- no belief probabilities in player output
- turn 2 is not treated as ordering another beer
- turn 3 consumes or transiently records drinking ale
- turn 4 can reveal allowed local information
- turn 5 is journal/internal memory, not ambiguous NPC speech
- final narrative aligns with admitted patch
- next turn packet reflects previous admitted consequences
```

This eval is the gate for resuming larger design work.

---

## 9. Reorganization Phases

### Phase A - Stabilize Status

Create:

```text
PROJECT_STATUS.md
```

It must state:

```text
Current main track: v0.6 agentic Python
Paused: UPF bridge
Baseline: v0.5 deterministic legacy engine
Primary eval: Greyfen 5-turn beer loop
Do not expand: new legacy proposer heuristics, bridge work, Teacher bottom-layer mutation
```

### Phase B - Move Docs First

Move or copy docs into:

```text
docs/plans/
docs/reviews/
docs/prompts/
docs/architecture/
docs/archive/
```

Suggested mapping:

```text
MetaRPG_Agent_ver0.6_plan.md -> docs/plans/
reviewVer0.6.1.md -> docs/reviews/
MetaRPG_Agent_story_prompt_reference.md -> docs/prompts/
ARCHITECTURE_REORG_PLAN.md -> docs/architecture/ after root copy is no longer needed
planVer0.*.md -> docs/archive/old_plans/
review_v0.2.1.md -> docs/archive/old_reviews/
```

Do not rewrite content during move.
Do not mix docs moves with code behavior changes.

### Phase C - Add Run Manifest And Event Logs

Update agentic runner to always emit:

```text
run_manifest.json
events.jsonl
errors.jsonl
summary.md
```

Any missing turn should be recorded as:

```text
turn_NNN_error.json
```

not silently skipped.

### Phase D - Stabilize Agentic Interfaces

Create:

```text
docs/architecture/v0.6_interfaces.md
```

Document:

```text
StoryPacket schema
WriterOutput schema
NarrativeClaim schema
AuditIssue schema
RewriteTask schema
AdmittedPatch schema
```

No agent prompt changes should alter these schemas without updating this doc and tests.

### Phase E - Fix Primary Eval Infrastructure

Required fixes:

```text
- 5-turn case support
- state continuity across turns
- non-empty player_output
- scorecard reads hard/medium/soft issues
- soft issues affect player experience score
- missing turns fail run manifest
```

### Phase F - Optional File Moves

Only after tests pass:

```text
move bridge files into metarpg/bridge/
move legacy files into metarpg/legacy/
move stable shared files into metarpg/core/
```

Use compatibility imports temporarily:

```python
# metarpg/engine.py
from metarpg.legacy.engine import *
```

Do not combine file moves with behavior changes.

---

## 10. Freeze Rules

Until primary eval is stable:

```text
No UPF work.
No Teacher code mutation.
No new scenario.
No new frontier/retrodiction integration into agentic path.
No new behavior categories in legacy proposer.
No broad refactor mixed with behavior fixes.
```

Allowed:

```text
schema stabilization
eval runner fixes
story packet continuity
auditor rule refinement
scorecard correctness
document moves
small compatibility wrappers
```

---

## 11. Definition Of Done

Architecture reorg is done when:

```text
- PROJECT_STATUS.md exists and names the active track.
- docs are grouped by purpose.
- runtime agentic runs emit manifest + summary.
- runtime agentic runs emit events.jsonl + errors.jsonl.
- Greyfen 5-turn eval runs without missing turn files.
- scorecards reflect soft/medium/hard issues truthfully.
- agentic interfaces are documented.
- bridge is marked paused.
- legacy deterministic engine still passes existing tests.
- no file move changes behavior.
```

---

## 12. Final Line

This reorg is a narrowing move.

The project should not try to prove every idea at once.

For now:

```text
One main line: v0.6 agentic Python.
One baseline: deterministic legacy core.
One paused line: UPF bridge.
One proof target: Greyfen 5-turn loop.
One artifact standard: manifest + turn drafts + scorecards + summary.
```

Once that is stable, the project can grow again without losing its center.
