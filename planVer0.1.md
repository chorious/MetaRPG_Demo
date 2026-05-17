# MetaRPG Demo v0.1 - Sonnet Execution Plan

## 0. One Sentence

Build a tiny **retrodictive reasonability engine**, not an AI dungeon: player actions update a local world slice, hidden truths keep Bayesian probabilities, and high-confidence explanations can be canonized later without violating locked facts.

## 1. Core Thesis

The demo should prove this loop:

```text
Raw text / cold archive
  -> hot reasonability matrix
  -> local action slice
  -> patch validation
  -> belief update
  -> possible retrodiction
  -> canonized delta
  -> rendered feedback
```

Compression is not for saving context. Compression is for **localization**:

```text
GlobalJudge(history, action) ~= LocalJudge(reasonability_slice, action)
```

The project succeeds if the system can judge and evolve a small story world without rereading all history every turn.

## 2. Non-Goals

Do not build a full RPG.
Do not build combat.
Do not build inventory beyond minimal props.
Do not rely on raw RAG as the main intelligence.
Do not let an LLM directly mutate canon.
Do not make JSON the conceptual center. JSON is allowed only as debug/export transport.

## 3. Minimal Scenario

Use one small village mystery:

```text
Place: The village of Greyfen
Core event: The old mine was sealed, but someone may have entered it recently.
NPCs:
- Mara: tavern keeper, evasive, may know more than she says
- Captain Rusk: village guard captain, may be pressuring Mara
- Iven: missing miner, maybe alive, maybe dead, maybe hiding
Locations:
- tavern
- old_mine_gate
- guard_post
- mara_cellar
```

The truth is not fully fixed at start. Some facts are hard canon; others are latent hypotheses.

## 4. Information Layers

Implement four layers.

### 4.1 Cold Archive

Append-only raw text log. Store every player input and rendered output. It is evidence, not runtime truth.

Suggested file/table:

```text
archive_events(id, turn, kind, text, touched_entities, timestamp)
```

### 4.2 Hard Canon

Facts that cannot be contradicted.

Examples:

```text
at(player, tavern)
at(mara, tavern)
sealed(old_mine)
said(mara, "the mine is sealed")
```

### 4.3 Hot Reasonability Matrix

A compact rule-bearing layer produced from history. This is the main runtime state.

It should contain:

```text
locked facts
knowledge partitions
relationship tensions
active motifs
frontier actions
local constraints
```

Represent it internally however is easiest, but expose/debug it as a compact DSL, not nested JSON.

Example debug format:

```text
@FACT at(player,tavern)
@FACT sealed(old_mine)
@KNOW mara knows sealed(old_mine)
@REL mara->player trust=.18 fear=.10 curiosity=.35
@MOTIF forbidden_place(old_mine) lure=.62 danger=.48
@MOTIF debtor_creditor(mara,rusk) pressure=.55 due=soon
@FRONTIER ask(mara,old_mine) | sneak(old_mine_gate) | confront(rusk,mara)
```

### 4.4 Belief / Latent Layer

Unfixed hidden truths with probabilities.

Example:

```text
H1 mara_knows_recent_entry     p=.45
H2 mara_entered_mine           p=.18
H3 rusk_pressures_mara         p=.35
H4 iven_alive_in_mine          p=.30
H5 iven_dead_and_hidden        p=.20
```

Future observations update these probabilities. When a hypothesis crosses a threshold and does not violate hard canon, it may become canon.

## 5. Turn Loop

Every turn should run this pipeline:

```text
1. Accept player action text
2. Detect touched entities and topics
3. Build local slice from hot matrix + relevant beliefs
4. Compile action into a structured patch
5. Validate patch against local rules and forbidden patterns
6. Apply accepted patch to canon/matrix
7. Update belief probabilities
8. If posterior is high, propose retrodictive explanation path
9. Validate explanation path
10. Canonize explanation if safe
11. Render feedback from canonized delta only
12. Append raw text to cold archive
```

Important boundary:

```text
LLM/compiler may propose.
Canon engine decides.
Renderer may dramatize, but may not create facts.
```

## 6. Patch DSL

Use a tiny patch DSL for debug. Example:

```text
TRY ask(player,mara,old_mine_recent_activity)
REQUIRES same_location(player,mara)
EFFECT event(player_asked_mara_about_mine)
EFFECT observe(mara_evasive_about_mine)
EFFECT rel_delta(mara,player,trust,+.04)
EFFECT belief_delta(mara_knows_recent_entry,+.10)
```

A failed action should explain which requirement failed.

Example:

```text
REJECT sneak(player,old_mine_gate)
WHY missing_required_location(player,old_mine_gate)
```

## 7. Rules For v0.1

Hard-code rules first. Do not overgeneralize.

Minimum rules:

```text
same_location(actor,target) required for direct conversation
cannot reveal secret unless speaker knows it
cannot enter locked location without key, force, permission, or stealth success
cannot canonize hidden fact if it contradicts locked speech/action facts
relationship trust/fear modifies confession probability
active motif modifies belief updates
```

Forbidden patterns:

```text
alive(X) and dead(X)
knows(X, secret) without source unless retcon path exists
entered(X, place, time) when place inaccessible and no access path exists
said(X, P) and canonized intentionally_lied(X, P) is allowed
said(X, P) and canonized P_false is allowed only if lie/mistake frame exists
```

## 8. Bayesian / Retrodiction Example

Initial observation:

```text
Mara says: "The mine is sealed. Nothing to see there."
```

Do not decide the full truth. Create/update beliefs:

```text
mara_knows_recent_entry += .10
mara_entered_mine += .04
rusk_pressures_mara += .05
```

Later observation:

```text
Rusk warns Mara: "Do not talk to outsiders about the mine."
```

Update:

```text
rusk_pressures_mara += .35
mara_knows_recent_entry += .25
mara_ignorant_about_mine -= .30
```

If `rusk_pressures_mara > .80`, propose retrodiction:

```text
RETROPATH rusk_pressures_mara
CAUSE mara_saw_rusk_near_mine(day_minus_2)
CAUSE rusk_threatened_mara(day_minus_1)
EXPLAINS mara_evasive_about_mine
```

Canonize only if validation passes.

## 9. Suggested Implementation Shape

Pick the simplest stack in this folder.

Recommended v0.1:

```text
Python CLI first
SQLite optional, plain files acceptable
No web UI until loop works
No external LLM dependency required for first pass
```

Suggested modules:

```text
metarpg/
  __init__.py
  models.py          # entities, facts, beliefs, motifs, patches
  dsl.py             # parse/render compact debug DSL
  world.py           # runtime state and local slice extraction
  rules.py           # validators and forbidden patterns
  beliefs.py         # Bayesian-ish updates and thresholds
  retrodict.py       # explanation path proposal + validation
  engine.py          # turn loop
  cli.py             # playable terminal demo
  scenarios/greyfen.py
  tests/
```

If using TypeScript instead, keep the same module boundaries.

## 10. First Milestone

Create a CLI where this works:

```text
> ask Mara about the mine
PATCH shown
VALIDATION accepted
BELIEF updates shown
NARRATION shown

> go to guard post
PATCH shown
CANON updated

> listen to Rusk and Mara
BELIEF rusk_pressures_mara rises
RETROPATH proposed/canonized if threshold reached
```

The player should be able to run 10-20 turns and see:

```text
hot matrix changing
beliefs changing
frontier changing
some facts staying locked
some hidden truth becoming canon later
```

## 11. Acceptance Criteria

Minimum acceptance:

```text
- CLI runs from project root
- Scenario initializes with 3 NPCs and 4 locations
- Every turn prints: local slice, patch, validation result, belief changes, canon delta, narration
- At least 5 actions are supported: ask, go, observe, confront, help/offer
- At least 1 action is rejected by rule validation
- At least 1 future event updates past hidden-state probability
- At least 1 retrodictive explanation path can be canonized
- Cold archive preserves raw text but normal turns do not reread full archive
- Tests cover validator, belief update, and retrodiction safety
```

Stretch acceptance:

```text
- Local slice extraction proves touched-entity locality
- Debug command prints hot matrix DSL
- Debug command prints hard canon vs soft beliefs
- Retrodiction can be rejected when it violates locked facts
```

## 12. How Sonnet Should Work

Implement in small commits or clear file batches:

```text
1. Scaffold project and CLI
2. Implement core data structures and scenario
3. Implement patch DSL and validators
4. Implement belief updates
5. Implement retrodiction proposal/validation
6. Add tests
7. Add README with run commands and design notes
```

Keep the demo small. The goal is not content volume. The goal is proving this mechanism:

```text
history -> local reasonability -> action patch -> belief update -> safe retrodiction -> canon
```

## 13. Design Mantra

```text
Raw text is cold evidence.
Hot glyphs are runtime compression.
Rules are compiled past.
Beliefs are uncollapsed truth.
Actions open probability space.
Future evidence can explain the past.
Canon is what survived validation.
```
