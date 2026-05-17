# planVer0.6.3 - MetaRPG Source Reorganization

## 0. Version Position

`v0.6.3` is a refactoring version.

It does not aim to add new narrative power.
It aims to make the existing v0.6 agentic pipeline maintainable enough that further narrative work can be judged clearly.

Current active direction:

```text
World Schema
+ Writer LLM
+ Translator / Hard Auditor
+ Soft Auditor
+ Editor
+ Teacher as rule curator
```

The immediate problem is not that the idea is wrong.
The problem is that the codebase now makes every issue look like every other issue:

```text
prompt issue
schema issue
runtime logging issue
state continuity issue
audit strictness issue
CLI issue
legacy engine issue
UPF bridge issue
```

`v0.6.3` should separate those concerns before adding more intelligence.

---

## 1. Core Judgment

The project should not perform a full physical package split first.

A big file move would create noise while the v0.6 runtime is still unstable.

The correct first refactor is:

```text
extract the active turn pipeline into stable Python interfaces
standardize runtime artifacts
make scripts thin wrappers
only then move legacy / bridge / core files
```

This means `v0.6.3` is not a cosmetic folder cleanup.
It is a control-surface cleanup.

---

## 2. Current Structural Problems

### 2.1 The Real Runner Is Not A Product Interface

Current symptoms:

```text
scripts/play_agentic.py owns live play behavior
scripts/agentic_5turn_smoke_test.py owns eval-ish behavior
metarpg/agentic/eval_runner.py owns another evaluation path
run_logger.py exists but is not yet the single artifact authority
scorecard.py exists but scoring is not yet the single judgment authority
```

This makes bugs hard to classify.

Example:

```text
turn 2 writer JSON failure
```

This can currently be caused by:

```text
Writer prompt too loose
Writer parser too brittle
script failing to retain raw output
logger not writing error artifacts
scorecard accepting incomplete output
```

A refactor must make these failures land in separate files and separate responsibilities.

### 2.2 Agentic Is Mostly Packaged, But Not Yet Orchestrated

Current `metarpg/agentic/` already contains useful components:

```text
schemas.py
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
run_logger.py
scorecard.py
eval_runner.py
```

But there is no single canonical function that means:

```text
run one agentic turn from player_input to final player_output and artifacts
```

That missing function is the main cause of drift.

### 2.3 Runtime Evidence Is Still Too Informal

The project is already learning from logs, but the logs are not strict enough.

Missing or weak artifact guarantees:

```text
every attempted turn must leave an artifact
every model failure must retain raw model text if available
every score must explain why it is high or low
soft issues must affect experience score
missing player output must fail loudly
run summary must expose missing turns
```

Without this, the project cannot distinguish:

```text
bad story
bad checker
bad parsing
bad state carryover
bad logging
```

### 2.4 Root Package Still Mixes Tracks

Current root package mixes:

```text
legacy deterministic engine
core world/reasoning primitives
UPF bridge
agentic dependencies
scenario data
```

Examples:

```text
metarpg/engine.py
metarpg/proposer.py
metarpg/assembler.py
metarpg/models.py
metarpg/world.py
metarpg/bridge.py
metarpg/bridge_session.py
metarpg/export_snapshot.py
```

This is not fatal yet, but it is becoming expensive.

The important point:

```text
root package cleanup should be delayed until v0.6 runner/logger contracts are stable
```

---

## 3. v0.6.3 Target

After `v0.6.3`, the project should have one obvious active path:

```text
metarpg-agentic
  -> metarpg.agentic.play_cli.main
  -> metarpg.agentic.runner.run_agentic_turn
  -> metarpg.agentic.run_logger.AgenticRunLogger
  -> runtime/agentic_runs/<run_id>/...
```

And one obvious test/eval path:

```text
python -m pytest tests/test_agentic_*.py tests/test_v061_regression.py
python scripts/agentic_5turn_smoke_test.py
```

The refactor is successful only if future debugging starts from artifacts, not from guessing.

---

## 4. Proposed Package Shape

### 4.1 Immediate Shape For v0.6.3

Only add/move what directly stabilizes the active path:

```text
metarpg/
  agentic/
    __init__.py
    schemas.py
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
    scorecard.py
    run_logger.py
    runner.py          # new canonical turn orchestration
    play_cli.py        # new canonical interactive CLI
    eval_runner.py
    rules/
      base_rules.yaml
      candidate_rules.yaml

scripts/
  play_agentic.py              # thin wrapper only
  agentic_5turn_smoke_test.py  # thin eval wrapper or compatibility script
  agentic_smoke_test.py        # compatibility script
```

This is the first important boundary.

### 4.2 Later Shape, Not Required In First Patch

After v0.6.3 stabilizes active behavior:

```text
metarpg/
  core/
    models.py
    world.py
    rules.py
    claims.py
    beliefs.py
    events.py
    hooks.py
    hookmatch.py
    hookgen.py
    frontier.py
    retrodict.py
    plot_graph.py
    plot_diagnose.py

  legacy/
    engine.py
    proposer.py
    assembler.py
    metaact.py
    narrator.py
    parsing.py
    cli.py
    session_logger.py

  bridge/
    bridge.py
    bridge_protocol.py
    bridge_session.py
    export_snapshot.py
```

Use compatibility wrappers when this move happens:

```python
# metarpg/engine.py
from metarpg.legacy.engine import *
```

Do not combine these physical moves with behavior changes.

---

## 5. New Canonical Interfaces

### 5.1 `metarpg.agentic.runner`

Create a single canonical runner module.

Required public interface:

```python
def run_agentic_turn(
    *,
    world,
    player_input: str,
    turn_index: int,
    run_logger=None,
    history=None,
    models=None,
    mode: str = "live",
):
    ...
```

The exact signature can be adjusted to local code, but the responsibility must be fixed.

It owns orchestration order:

```text
1. build story packet
2. call Writer
3. parse Writer output
4. translate narrative claims
5. scan text
6. hard audit
7. soft audit
8. produce editor tasks if needed
9. repair if configured
10. commit admitted patch
11. score draft
12. write artifacts
13. return turn result
```

It must not own:

```text
prompt text beyond calling agents
low-level model HTTP behavior
filesystem layout details beyond logger calls
CLI input loop
```

### 5.2 `metarpg.agentic.play_cli`

Move live play loop out of `scripts/play_agentic.py`.

Required behavior:

```text
create run_id
create AgenticRunLogger
load initial Greyfen world
read player input
call run_agentic_turn
print player_output
handle failure by printing concise error and preserving artifact
write summary on exit
```

Then keep the script as a wrapper:

```python
from metarpg.agentic.play_cli import main

if __name__ == "__main__":
    main()
```

### 5.3 `metarpg.agentic.run_logger`

Make logger the only code that understands runtime artifact layout.

Required methods:

```text
start_run
log_event
log_error
write_turn
write_error_turn
write_scorecard
write_manifest
write_summary
finish_run
```

Rules:

```text
Every attempted turn gets either turn_NNN.json or turn_NNN_error.json.
Raw model output is stored in the turn artifact, not lost in console output.
errors.jsonl stays compact and points to the artifact.
summary.md is generated even after failure.
```

### 5.4 `metarpg.agentic.scorecard`

Make scorecard the single place where acceptance is computed.

It should read:

```text
hard_audit
soft_audit
editor_tasks
rewrite_history
player_output
candidate_patch
admitted_patch
runtime errors
```

It should fail or reduce score for:

```text
missing player_output
missing turn artifact
hard_audit passed=false
writer/parser exception
medium issue count above threshold
soft issue count above threshold
repair loop exhausted
candidate_patch not reflected in final text
final text contains debug/schema language
```

The scorecard must not say `experience=1.00` when the run obviously produced a rough user-facing experience.

---

## 6. Hard Boundary Between Agents

`v0.6.3` should preserve the conceptual architecture but make it enforceable in code.

### 6.1 Writer

Writer responsibility:

```text
produce vivid local narrative
honor packet constraints
produce candidate patch proposals
return valid structured JSON
```

Writer must not:

```text
commit world state
invent hidden truth as revealed fact
decide whether its own claims are valid
silently output partial JSON without artifact capture
```

### 6.2 Translator

Translator responsibility:

```text
turn natural language into structured narrative claims
attach evidence spans
be stricter about concrete claims than ambient prose
```

Translator must not:

```text
judge story quality
repair prose
commit patch
```

### 6.3 Hard Auditor

Hard Auditor responsibility:

```text
check structural alignment between claims, patch, packet, and world
```

Hard Auditor should fail hard on:

```text
named NPC speech without patch or allowed dialogue support
hard state mutation without admitted/candidate effect
hidden fact leak
contradiction of locked world fact
specific absent entity performing an action
raw debug/schema exposure in player text
```

Hard Auditor should not fail hard on:

```text
reasonable ambient tavern background
non-committed mood description
minor prop color or texture
soft tonal weakness
```

This is the important refinement from the recent logs:

```text
turn_004 unnamed tavern guests are mostly ambient
t度rn_005 notebook/ink is medium or soft unless it becomes committed world state
turn_003 "再来一杯?" without corresponding speech/effect support is a real alignment issue
```

### 6.4 Soft Auditor

Soft Auditor responsibility:

```text
judge player-facing quality
judge continuity feeling
judge whether prose feels like story or machinery
```

Soft Auditor output must affect scorecard.
Otherwise it becomes decorative.

### 6.5 Editor

Editor responsibility:

```text
turn audit issues into local rewrite tasks
cut failing segments precisely
preserve passing segments
feed concrete instructions back to Writer or repair loop
```

Editor must not default to full-turn rewrite.

### 6.6 Teacher

Teacher responsibility:

```text
review recurring issues
promote stable lessons into candidate rules
校对 candidate rules before humans decide whether to accept them
```

Teacher must not:

```text
mutate core code automatically
change hard bottom-layer rules during live play
turn every one-off failure into a permanent rule
```

Teacher is a rule curator, not a runtime authority.

---

## 7. Refactor Phases

### Phase A - Freeze And Baseline

Goal:

```text
prove current behavior before changing structure
```

Tasks:

```text
run full pytest
record current failures if any
record one live play failure artifact if available
confirm PROJECT_STATUS.md states v0.6 agentic Python as main track
```

Acceptance:

```text
baseline test result is known
no behavior changes yet
```

### Phase B - Extract Canonical Runner

Goal:

```text
move active turn orchestration into metarpg.agentic.runner
```

Tasks:

```text
create runner.py
move reusable turn pipeline out of scripts/play_agentic.py
ensure Writer exceptions become structured error turn drafts
ensure raw_writer_output survives when available
return a structured result object or dict
```

Acceptance:

```text
scripts/play_agentic.py can call runner
existing agentic tests pass
turn failure writes turn_NNN_error.json
```

### Phase C - Normalize Logging

Goal:

```text
make runtime artifacts trustworthy enough for debugging
```

Tasks:

```text
make AgenticRunLogger authoritative for paths
write run_manifest.json at start and finish
write events.jsonl for every stage
write errors.jsonl for exceptions
write summary.md on normal exit and failure
add tests for missing-turn recording
```

Acceptance:

```text
no attempted turn disappears
writer JSON failure leaves raw model text if captured
summary shows completed, failed, and missing turns
```

### Phase D - Normalize Scorecard

Goal:

```text
stop score inflation
```

Tasks:

```text
score hard failures as unacceptable
score missing player_output as unacceptable
make soft issues reduce player_experience_score
make medium issues reduce grounding or continuity score
include issue counts in scorecard_NNN.json
include repair round count
```

Acceptance:

```text
rough logs cannot receive experience=1.00 by default
scorecard explains every deduction
primary eval fails when a turn is missing
```

### Phase E - Add Proper CLI Entry Point

Goal:

```text
make the active playable mode a package command, not a script accident
```

Tasks:

```text
create metarpg.agentic.play_cli
add pyproject script: metarpg-agentic = "metarpg.agentic.play_cli:main"
keep scripts/play_agentic.py as compatibility wrapper
update README / PROJECT_STATUS if needed
```

Acceptance:

```text
metarpg-agentic starts live play
scripts/play_agentic.py still works
both paths create identical runtime artifacts
```

### Phase F - Scenario And Eval Cleanup

Goal:

```text
make Greyfen 5-turn loop a real gate
```

Tasks:

```text
ensure metarpg.scenarios.greyfen provides canonical initial state
make eval_runner consume the same runner as live play
keep the 5-turn smoke case in one place
make missing turn files fail the eval
make state continuity visible in next StoryPacket
```

Acceptance:

```text
live play and smoke eval use same turn runner
Greyfen 5-turn run has continuous turn files
turn 3 drink action is reflected in later packet or recent_events
turn 5 internal note/journal behavior is not treated as NPC speech
```

### Phase G - Documentation Cleanup

Goal:

```text
keep design memory useful
```

Tasks:

```text
keep plans under docs/plans
keep reviews under docs/reviews
keep prompt references under docs/prompts
keep stable interface docs under docs/architecture
avoid new root docs except allowed root files
```

Acceptance:

```text
new v0.6.3 plan lives in docs/plans
root does not accumulate new plan/review/prompt files
```

### Phase H - Deferred Physical Package Moves

Goal:

```text
split root package only after active path stabilizes
```

Tasks:

```text
move bridge files into metarpg/bridge/
move legacy files into metarpg/legacy/
move stable shared world/reasoning files into metarpg/core/
add compatibility wrappers
run full pytest after each move group
```

Acceptance:

```text
imports remain compatible
full pytest passes
file moves are not mixed with behavior changes
```

---

## 8. What Not To Do In v0.6.3

Do not:

```text
resume UPF bridge work
add new story systems
add new scenario content
let Teacher mutate bottom-layer code
perform a full root package move before runner/logger are stable
rewrite all prompts at once
make Hard Auditor a packet whitelist
make Soft Auditor decorative
```

The project is slow now because every turn crosses too many unresolved boundaries.
The fix is not another layer.
The fix is to make the current layers accountable.

---

## 9. Testing Plan

Minimum tests after each phase:

```text
python -m pytest tests/test_agentic_writer.py tests/test_v061_regression.py
python -m pytest tests/test_agentic_*.py
python -m pytest
```

New tests recommended for v0.6.3:

```text
test_runner_writes_error_turn_on_writer_json_failure
test_run_logger_writes_manifest_events_errors_summary
test_scorecard_penalizes_soft_issues
test_scorecard_fails_missing_player_output
test_eval_fails_missing_turn_file
test_live_and_eval_use_same_runner_contract
```

Test philosophy:

```text
Do not test LLM creativity.
Test contracts, artifacts, and acceptance behavior.
```

---

## 10. Definition Of Done

`v0.6.3` is done when:

```text
metarpg.agentic.runner exists and is the only canonical turn orchestration path
metarpg.agentic.play_cli exists or scripts/play_agentic.py is reduced to a thin wrapper
run_logger writes manifest, events, errors, turn artifacts, scorecards, summary
writer/parser failures preserve raw model output when available
scorecard reflects hard, medium, and soft issues truthfully
Greyfen 5-turn eval uses the same runner as live play
missing turns fail visibly
full pytest passes
root docs do not accumulate new plans/reviews/prompts
UPF remains paused
legacy deterministic tests still pass
```

---

## 11. Implementation Order

Recommended commit sequence:

```text
1. docs: add planVer0.6.3 refactor plan
2. tests: add artifact/scorecard regression tests
3. agentic: extract runner from play_agentic script
4. agentic: make run_logger authoritative for runtime artifacts
5. agentic: make scorecard acceptance strict and explanatory
6. cli: add metarpg-agentic entry point and keep script wrapper
7. eval: route Greyfen smoke test through canonical runner
8. docs: update PROJECT_STATUS / README command references
9. optional: move bridge package with compatibility wrappers
10. optional: move legacy/core packages with compatibility wrappers
```

This order keeps behavior visible while structure changes.

---

## 12. Final Direction

`v0.6.3` should make the project smaller in the developer's head.

After this refactor, the question should no longer be:

```text
Where did the roughness come from?
```

It should become one of these concrete questions:

```text
Did StoryPacket omit necessary local context?
Did Writer violate output contract?
Did Translator over/under-extract claims?
Did Hard Auditor misclassify grounding?
Did Soft Auditor catch rough experience?
Did Editor localize repair correctly?
Did Committer update world continuity?
Did Logger preserve enough evidence?
Did Scorecard tell the truth?
```

That is the real purpose of the refactor.
