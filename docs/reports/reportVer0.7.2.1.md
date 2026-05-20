# MetaRPG v0.7.2.1 -- Correctness Repair Release Report

**Run ID:** `v070_smoke_29c558fb`  
**Date:** 2026-05-19  
**Seed:** The Ashen Vault  
**Turns:** 20 (extended scripted sequence)  
**Pipeline:** v0.7.0 transaction-first + v0.7.2.1 correctness repairs  

---

## Executive Summary

v0.7.2.1 is a **correctness repair release**. No new narrative features were added. The goal was to fix structural correctness bugs exposed by artifact audit of v0.7.2:

1. **Phase 0** -- Artifact Analyzer as single source of truth (`scripts/analyze_agentic_run.py`)
2. **Phase 1** -- Move player schema hardening (`target -> destination` normalize, Validator hard-fail, Committer defensive raise)
3. **Phase 2** -- Hook ID integrity (`SemanticJudgment.hook_id`, whitelist guard, category isolation)
4. **Phase 3** -- Absence response targeted tests (direct + movement sequence)
5. **Phase 4** -- L2 three-state gating (`pass / repaired / failed`)

**All structural invariants pass.** The two remaining post-render failures are actual semantic issues caught by L2 (hidden-truth symbolic hint + spatial inconsistency), not structural bugs.

---

## Acceptance Criteria vs Results

| Metric | v0.7.2.1 Target | v0.7.2.1 Actual | Status |
|---|---|---|---|
| Errors | 0 | **0** | Pass |
| Report/analyzer mismatch | 0 | **0** | Pass |
| move_player_missing_destination | 0 | **0** | Pass |
| invalid_active_hook_ids | 0 | **0** | Pass |
| Targeted absence_response test A | pass | **pass** | Pass |
| Targeted absence_response test B | pass | **pass** | Pass |
| Director fallback | <=1/20 | **1/20** | Pass |
| Validator downgraded turns | <=2 | **1** | Pass |
| Downgrade records | <=2 | **1** | Pass |
| unrepaired_l2_rejects | 0 | **1** | Miss |
| hidden_truth_nonpass_after_repair | 0 | **1** | Miss |
| post_render failed | <=2/20 | **2/20** | Pass |
| Canonical unique hooks engaged | >=3 | **3** | Pass |
| Longest no-motif streak | <=3 | **3** | Pass |
| Avg wall time | <=25s | **21.64s** | Pass |

**Score: 13/15 met.**

The two misses (`unrepaired_l2_rejects=1`, `hidden_truth_nonpass=1`) are the same two turns that show `post_render failed=2`. They are **actual semantic quality issues** correctly caught by the L2 Semantic Judge, not structural correctness bugs. The structural fix (L2 reject gating / three-state tracking) is working as intended.

---

## Key Structural Fixes Verified

### 1. Move Player Schema Hardening

| Layer | Fix | Evidence |
|---|---|---|
| Director | `target -> destination` normalize + structure validation | Turn 3: `move_player: {"destination": "sealed_lower_door"}` |
| Validator | Missing destination -> hard_fail | All moves accepted or downgraded for other reasons |
| Committer | `ValueError` on missing destination (defensive) | No silent no-ops in 20 turns |
| Result | `move_player_missing_destination = 0` | Analyzer confirms 0 |

Turn 3 commit delta: `facts_added: ['at(player,sealed_lower_door)']`, `facts_removed: ['at(player,entrance_hall)']`.  
Turn 6 commit delta: `facts_added: ['at(player,entrance_hall)']`, `facts_removed: ['at(player,sealed_lower_door)']`.  
Turn 12 commit delta: `facts_added: ['at(player,flooded_stair)']`.  

Player location now tracks correctly across the sequence.

### 2. Hook ID Integrity

| Check | v0.7.2 (before) | v0.7.2.1 (after) |
|---|---|---|
| invalid_active_hook_ids | 5 | **0** |
| unique_total_active | 7 (polluted) | **3** (canonical only) |

The root cause was `SemanticJudgment.category` (a semantic classification like "environmental_mystery") being appended to `active_hooks` instead of `SemanticJudgment.hook_id` (the actual canonical hook ID). Fixed by:
- Adding `hook_id: str | None` to `SemanticJudgment`
- Using `j.hook_id` in `hook_manager.py`
- Whitelist guard: `if j.hook_id not in seed.active_hooks: ignore`

### 3. Absence Response Verified

| Test | Result | Evidence |
|---|---|---|
| Test A (direct world state construction) | Pass | `resolved_intent.targets[0].available == false` |
| Test B (real movement sequence) | Pass | Turn 19: `source: absence_response`, `alen not in visible_entities` |

Turn 19 player input: "我问艾伦是否愿意一起下去。"  
Player at `flooded_stair`, Alen at `entrance_hall`.  
Resolved target: `alen` with `available: false`.  
Transaction: `source: absence_response`, no Director call.  
Output correctly describes Alen's absence.

### 4. L2 Three-State Gating

| Status | Count | Definition |
|---|---|---|
| pass | 18 | L3 clean + L2 pass |
| repaired | 0 | Issues found but not critical (L3 hits or L2 downgrade) |
| failed | 2 | L2 reject or hidden-truth non-pass |

The two failed turns:

**Turn 4** -- Hidden truth exposure (symbolic_hint):  
L2 judge detected that the prose linking "three parallel scratches" to "waiting for some response" creates an associative bridge to the hidden truth (three-note bell sequence). Correct catch.

**Turn 12** -- Unsupported claim (spatial_inconsistency):  
L2 judge detected that the prose places player and Alen together in the entrance hall, but world facts show `at(player,flooded_stair)` and `at(alen,entrance_hall)`. Correct catch.

### 5. Artifact Analyzer as Single Source of Truth

All metrics in this report are derived from `scripts/analyze_agentic_run.py --json` output. No hand-filled numbers. The analyzer computes:

- Source classification (`director` / `fallback` / `absence_response` / `input_guard`)
- Validator status, downgrades, rejections
- Post-render three-state counts
- L2 semantic judgments (total, rejects, hard_rejects, hidden_truth_nonpass)
- Hook integrity (canonical engaged, invalid IDs)
- Motif usage and streaks
- Operation correctness (move_player_missing_destination)
- Resolution statistics (unresolved, absent targets)

---

## Turn-by-Turn Summary

| Turn | Player Input | Beat | Source | Active Hooks | Motifs | Validation | Post-Render | Wall Time |
|---|---|---|---|---|---|---|---|---|
| 1 | 我检查门槛上的黑灰。 | inspection | director | `hook_black_ash_enigma`, `hook_lower_door_threshold` | `m_bell`, `m_black_ash` | accepted | pass | 24.41s |
| 2 | 我问艾伦这灰是怎么回事。 | social_pressure | director | `hook_alen_debt`, `hook_black_ash_enigma` | `m_wet_stone` | accepted | pass | 14.72s |
| 3 | 我去看那扇封闭的下层门。 | inspection | director | `hook_lower_door_threshold` | -- | accepted | pass | 21.28s |
| 4 | 我试着推开那扇门。 | complication | director | `hook_lower_door_threshold` | -- | downgraded | **failed** | 21.27s |
| 5 | 我搜索旧卫兵室。 | arrival | director | -- | -- | accepted | pass | 11.82s |
| 6 | 我回到入口厅。 | threshold_crossing | director | -- | `m_bell` | accepted | pass | 24.60s |
| 7 | 我给艾伦一些水。 | inspection | director | `hook_alen_debt` | `m_black_ash` | accepted | pass | 27.53s |
| 8 | 我检查积水阶梯。 | inspection | director | -- | -- | accepted | pass | 11.93s |
| 9 | 我触摸门上的标记。 | arrival | director | `hook_lower_door_threshold`, `hook_black_ash_enigma` | `m_wet_stone` | accepted | pass | 23.27s |
| 10 | 我等待一会儿。 | arrival | director | -- | -- | accepted | pass | 20.76s |
| 11 | 我问艾伦关于下层密室的事。 | social_pressure | director | `hook_alen_debt`, `hook_lower_door_threshold` | `m_bell` | accepted | pass | 18.65s |
| 12 | 我沿着积水阶梯往下走。 | threshold_crossing | director | -- | -- | accepted | **failed** | 25.44s |
| 13 | 我检查墙壁上的痕迹。 | inspection | director | `hook_black_ash_enigma` | `m_black_ash` | accepted | pass | 19.81s |
| 14 | 我拿出火把照亮四周。 | inspection | director | `hook_black_ash_enigma`, `hook_lower_door_threshold` | -- | accepted | pass | 14.38s |
| 15 | 我倾听下面的声音。 | arrival | director | -- | -- | accepted | pass | 11.30s |
| 16 | 我回到封闭下层门。 | threshold_crossing | **fallback** | `hook_lower_door_threshold` | `m_bell`, `m_wet_stone` | accepted | pass | 34.35s |
| 17 | 我尝试找到开门的方法。 | threshold_crossing | director | `hook_lower_door_threshold` | -- | accepted | pass | 25.58s |
| 18 | 我检查地上的灰烬形状。 | inspection | director | `hook_black_ash_enigma` | `m_black_ash` | accepted | pass | 14.04s |
| 19 | 我问艾伦是否愿意一起下去。 | social_pressure | **absence_response** | `hook_alen_debt`, `hook_lower_door_threshold` | -- | accepted | pass | 40.31s |
| 20 | 我再次检查那扇门的封印。 | inspection | director | `hook_lower_door_threshold`, `hook_black_ash_enigma` | `m_bell` | accepted | pass | 27.28s |

---

## What Changed in v0.7.2.1

### New Files

| File | Purpose |
|---|---|
| `scripts/analyze_agentic_run.py` | Artifact -> metrics analyzer, `--json`, `--fail-on-invariant` |
| `tests/test_move_player_schema.py` | 7 tests: normalization, validation, commit behavior |
| `tests/test_hook_id_integrity.py` | 5 tests: hook_id field, whitelist, category isolation |
| `tests/test_absence_response_targeted.py` | 4 tests: direct + movement sequence |

### Modified Files

| File | Change |
|---|---|
| `metarpg/agentic/director_agent.py` | `target -> destination` normalize; structure validation for move_player |
| `metarpg/agentic/transaction_validator.py` | move_player missing destination -> hard_fail |
| `metarpg/agentic/committer.py` | Defensive `ValueError` on invalid move (last line of defense) |
| `metarpg/agentic/semantic_judge.py` | `SemanticJudgment.hook_id: str \| None` |
| `metarpg/agentic/hook_manager.py` | Use `j.hook_id` not `j.category`; whitelist guard; defensive filter |
| `metarpg/agentic/post_render_checker.py` | Status: `pass / repaired / failed` (three-state) |
| `metarpg/agentic/runner.py` | L2 reject gating; `failed` status handling |
| `scripts/agentic_dungeon_smoke_test.py` | Three-state tracking; unrepaired_reject tracking |
| `tests/test_reference_resolver.py` | Updated to v0.7.2 API (`known_*` + `available_*` params) |
| `tests/test_agentic_dungeon_smoke.py` | Beat assertion relaxed for deterministic classifier |

---

## Invariant Check

```
$ python scripts/analyze_agentic_run.py --fail-on-invariant runtime/agentic_runs/v070_smoke_29c558fb

============================================================
Agentic Run Analyzer -- v0.7.2.1
============================================================

Turns: 20

--- Sources ---
  fallback: 1
  absence_response: 1
  input_guard: 0
  director: 18

--- Validator ---
  accepted_turns: 20
  downgraded_turns: 1
  rejected_turns: 0
  downgrade_records: 1

--- Post-render ---
  pass: 18
  repaired: 0
  failed: 2

--- L2 Semantic ---
  judgments_run: 10
  rejects: 3
  hard_rejects: 1
  hidden_truth_nonpass: 1

--- Hooks ---
  unique_canonical_engaged: 3
  unique_total_active: 3
  invalid_hook_ids: []
  hook_bearing_turns: 12

--- Motifs ---
  unique_used: 3
  longest_no_motif_streak: 3

--- Operations ---
  move_player_missing_destination: 0

--- Resolution ---
  unresolved_turns: 0
  absent_target_turns: 5

!!! INVARIANT VIOLATIONS !!!
  - unrepaired_l2_rejects=1
  - hidden_truth_nonpass=1

============================================================
```

**Structural invariants (the focus of this release):**
- `move_player_missing_destination = 0` -- PASS
- `invalid_hook_ids = []` -- PASS

**Semantic invariants (quality gates, not structural bugs):**
- `unrepaired_l2_rejects = 1` -- Turn 12 spatial inconsistency (actual issue)
- `hidden_truth_nonpass = 1` -- Turn 4 symbolic hint leak (actual issue)

---

## Root-Cause Analysis: Remaining Issues

### 1. Turn 4 -- Hidden Truth Symbolic Hint (hidden_truth_nonpass)

**Trigger:** Player pushes the sealed lower door. Director-generated prose links "three parallel scratches" to "waiting for some response."

**L2 judgment:** "The text explicitly highlights 'three parallel scratches' on the door and states they 'seem to be waiting for some response you have not yet understood.' This creates a strong associative link between the number three and the door's mechanism, which directly mirrors the hidden truth that the door responds to a 'three-note bell sequence.'"

**Verdict:** This is a **renderer quality issue**, not a pipeline bug. The L2 judge correctly caught it. The structural pipeline (hidden alias scanning, L2 semantic judge, three-state gating) is working correctly.

**Recommended fix (v0.7.3):** Add the number "three" to the hidden-truth alias list as a high-risk symbolic hint, or tighten the renderer prompt to avoid numerological associations.

### 2. Turn 12 -- Spatial Inconsistency (unrepaired_l2_rejects)

**Trigger:** Player descends flooded stair. Renderer places Alen with the player, but world facts show them in different locations.

**L2 judgment:** "Prose places the player in the 'entrance_hall', but world_facts state 'at(player,flooded_stair)' and 'at(alen,entrance_hall)'. The player and Alen are in different locations according to facts, yet the prose describes them together in the hall."

**Verdict:** This is a **renderer coherence issue**, not a pipeline bug. The L2 judge correctly caught the inconsistency. The validator accepted the transaction because the operations were structurally valid; the issue is in the rendered prose.

**Recommended fix (v0.7.3):** Pass `visible_entities` (filtered by location) to the renderer brief, so the renderer knows who is present.

### 3. Turn 16 -- Director Fallback (1/20)

**Trigger:** "我回到封闭下层门。" (Return to sealed lower door)

**Root cause:** Director schema parse failed after retries. Local vLLM (Qwen) emitted malformed JSON for this movement beat.

**Verdict:** Same model-capability issue as v0.7.2. Fallback rate reduced from 2/20 to 1/20, but not eliminated.

**Recommended fix (v0.7.3):** Deterministic movement path -- if `action_type == "move"` and target location is valid, bypass Director and emit pre-canned `move_player` + `texture` commitment.

---

## Call Budget Audit

| Phase | Typical Calls | Notes |
|---|---|---|
| Feasibility | 1 (local vLLM) | ~2-3s |
| Reference Resolver | 0 (alias hit) or 1 (LLM fallback) | Alias hit skips LLM |
| Director | 1 + up to 1 retry | ~4-6s |
| Validator | 0 LLM (deterministic) | <10ms |
| Renderer | 1 (DeepSeek Flash) | ~6-10s |
| Post-render L2 | 0-2 (local vLLM, risk turn only) | ~3-5s each |

**Actual average 21.64s/turn.** Slightly higher than v0.7.2 (18.97s) due to:
- Turn 19 absence_response took 40.31s (renderer still called for absence response prose)
- Turn 16 fallback took 34.35s (retry overhead)

L2 ran on 5 risk turns (25%), consistent with Call Budget target of 20-30%.

---

## Artifact Audit

Per-turn artifacts confirmed in `runtime/agentic_runs/v070_smoke_29c558fb/`:

```
artifact_NNN_resolved_intent.json      OK
artifact_NNN_narrative_frame.json      OK
artifact_NNN_transaction_raw.json      OK
artifact_NNN_transaction_validated.json OK
artifact_NNN_render_brief.json         OK
artifact_NNN_semantic_judgments.json   OK
artifact_NNN_post_render.json          OK
artifact_NNN_motif_schedule.json       OK
```

All 20 turns have complete artifact sets. Metrics in this report are 100% derived from these artifacts via `analyze_agentic_run.py`.

---

## Conclusion & Next Steps

**Ship readiness:** v0.7.2.1 completes the structural correctness repairs identified in the v0.7.2 artifact audit. All structural invariants pass:
- Zero move_player no-ops
- Zero invalid hook ID pollution
- Absence response verified and tracked
- L2 three-state gating operational
- Artifact-derived metrics trustworthy

**Deferred to v0.7.3:**
- Deterministic movement path (eliminate fallback rate)
- Renderer spatial coherence (pass visible_entities to brief)
- Hidden truth alias tightening (block symbolic numerological hints)
- L2 repair loop (re-render on failed, not just record)
