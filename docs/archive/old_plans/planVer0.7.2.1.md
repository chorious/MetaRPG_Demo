# MetaRPG v0.7.2.1 -- Correctness Repair Release

## Context

v0.7.2 review (`docs/reviews/reviewVer0.7.2.md`) based on artifact recalculation found multiple inconsistencies between report metrics and runtime facts. The core issues were not missing features, but **structural correctness bugs**:

- move_player schema no-op bug (`target` parameter not normalized to `destination`, committer silently swallowed it)
- semantic judge's `category` mistakenly used as `hook_id`, polluting `active_hooks`
- L2 reject only recorded but not closed (15 light_repair written as 2 in report)
- absence_response not triggered due to move bug causing player location not updating
- report metrics not automatically computed from artifacts

v0.7.2.1 is a **correctness repair release**, no new narrative features added. Goal: make artifacts, reports, world state, and semantic judgments consistent.

---

## Phase 0 -- Artifact Analyzer (Single Source of Truth)

**Goal:** Establish artifacts as the single source of truth for automatic metric computation.

**Deliverables:**
- `scripts/analyze_agentic_run.py`: Reads artifact JSON from `runtime/agentic_runs/<run_id>/`, outputs metrics
- CLI args:
  - `--json`: Machine-readable JSON output (for CI / smoke test / report consumption)
  - `--fail-on-invariant`: Non-zero exit code if invariant violations found (invalid hook id / move missing destination / unrepaired L2 reject)
- Metrics computed:
  - turns, errors, fallback_count
  - absence_response_count, input_guard_count
  - move_player_missing_destination_count
  - validator accepted/downgraded/rejected, downgrade_record_count
  - post_render pass/repaired/failed (three-state, see Phase 4)
  - l2_judgment_count, l2_reject_count, hidden_truth_nonpass_count
  - invalid_active_hook_ids, unique_canonical_hooks_engaged
  - hook_bearing_turns, motifs_used, longest_no_motif_streak
  - avg_wall_time from events

**Acceptance:**
- `python scripts/analyze_agentic_run.py runtime/agentic_runs/v070_smoke_9d1b9af2` output matches review recalculation results
- `python scripts/analyze_agentic_run.py --json --fail-on-invariant runtime/agentic_runs/<run_id>` can be directly called by smoke test
- Report metric tables must reference analyzer output, no hand-filled numbers

---

## Phase 1 -- Move Operation Schema Hardening

**Goal:** Eliminate move_player no-op.

**Deliverables:**
1. `metarpg/agentic/director_agent.py` `_parse_transaction()`:
   - Add `target -> destination` normalization (existing only had `target_location -> destination`)
   - `_validate_structure()` add: move_player must contain `destination` after normalization

2. `metarpg/agentic/transaction_validator.py` `_check_operation()`:
   - `move_player` missing `destination` => hard_fail
   - `move_player destination` does not exist => hard_fail (already existed)

3. `metarpg/agentic/committer.py` `_apply_operation()`:
   - When move_player missing destination, **do not silently return**
   - Defensive fail loudly: raise `ValueError("move_player missing destination")` or record `commit_error`
   - Note: Validator should already block, committer is last line of defense

4. `tests/test_move_player_schema.py`:
   - `test_move_player_target_normalized_to_destination`
   - `test_move_player_missing_destination_hard_fails`
   - `test_move_player_commit_changes_player_location`

**Acceptance:**
- 20-turn artifact shows `move_player_missing_destination = 0`
- All move_player produce `at(player, destination)` delta or are rejected

---

## Phase 2 -- Hook ID Integrity

**Goal:** `active_hooks` always contains only canonical seed hook ids.

**Deliverables:**
1. `metarpg/agentic/semantic_judge.py`:
   - `SemanticJudgment` add `hook_id: str | None = None` (hidden-truth / render-claim judgments don't need hook_id)
   - `_call_judge()` parser extracts `hook_id` field from JSON response, only `judge_hook_relevance()` output requires `hook_id`

2. `metarpg/agentic/hook_manager.py` `_match_hooks_v071()`:
   - Use `j.hook_id` (real hook id) not `j.category` when appending to `matched`
   - `semantic_judgments` record stores `"hook_id"` as real id, `"category"` as semantic classification
   - **Whitelist guard**: `if j.hook_id not in seed.active_hooks: ignore + log`, never let non-canonical id into active_hooks
   - Defensive guard: `set(active_hooks) <= set(seed.active_hooks.keys())`

3. `tests/test_hook_id_integrity.py`:
   - `test_semantic_judgment_returns_real_hook_id`
   - `test_active_hooks_only_canonical_ids`
   - `test_non_canonical_hook_id_ignored`
   - `test_category_not_polluting_active_hooks`

**Acceptance:**
- `invalid_active_hook_ids = 0`
- `unique hooks engaged <= len(seed.active_hooks)`

---

## Phase 3 -- Absence Response Targeted Tests

**Goal:** Prove known-but-unavailable target can trigger absence_response.

**Deliverables:**
- `tests/test_absence_response_targeted.py`, containing two tests:

  **Test A -- Direct world state construction:**
  ```
  Given: player at flooded_stair, alen at entrance_hall
  When: player_input = "我问艾伦关于下层密室的事。"
  Then:
    resolved_intent.targets[0].canonical_id == "alen"
    resolved_intent.targets[0].available == false
    runner emits source:absence_response transaction
    Director is not called
  ```

  **Test B -- Real movement sequence:**
  ```
  Given: player at entrance_hall (with alen)
  When: player moves to flooded_stair (valid move_player)
  Then: player location == flooded_stair, alen not in visible_entities
  When: player_input = "我问艾伦关于下层密室的事。"
  Then: absence_response triggered
  ```

**Acceptance:**
- Both targeted tests must pass
- Test B proves Phase 1 fix actually changes player location
- If 20-turn script creates absent target, artifact must show `source:absence_response`
- If 20-turn does not create absent target, report must not claim absence_response > 0

---

## Phase 4 -- L2 Reject Gating / Repair

**Goal:** L2 reject no longer treated as pass.

**Status semantics redefinition (three-state):**
- `pass` -- Initial check passed (L3 clean + L2 pass)
- `repaired` -- Issues found but not critical (L3 hits or L2 downgrade)
- `failed` -- Still reject / hidden truth non-pass after repair, or repair not attempted

**Deliverables:**
1. `metarpg/agentic/post_render_checker.py`:
   - Return status changed from `pass / light_repair` to `pass / repaired / failed`
   - `failed` = L2 reject or hidden-truth non-pass and not actually repaired to pass

2. `metarpg/agentic/runner.py`:
   - When post-render returns `failed`, that turn does not count as pass
   - Minimum: fail closed (unrepaired reject = failed)
   - Optional: generate repair brief, call Flash repair once, then run checker again; still reject => failed

3. `scripts/agentic_dungeon_smoke_test.py`:
   - Track three states: `pass_count / repaired_count / failed_count`
   - Track `unrepaired_l2_rejects` and `hidden_truth_nonpass_after_repair`
   - Report `post_render pass` only counts `pass` state, `repaired` listed separately, not counted as pass

**Acceptance:**
- `unrepaired_l2_rejects = 0`
- `hidden_truth_nonpass_after_repair = 0`
- `post_render failed <= 2/20`
- avg wall time <= 25s (repair calls increase variance, target relaxed)

---

## Phase 5 -- Re-run 20-turn + Report v0.7.2.1

**Goal:** Generate trustworthy report using analyzer.

**Acceptance table:**

| Metric | v0.7.2.1 Target |
|---|---:|
| errors | 0 |
| report/analyzer mismatch | 0 |
| move_player_missing_destination | 0 |
| invalid_active_hook_ids | 0 |
| targeted absence_response test A | pass |
| targeted absence_response test B | pass |
| Director fallback | <=1/20 |
| validator downgraded turns | <=2 |
| downgrade records | <=2 |
| unrepaired_l2_rejects | 0 |
| hidden_truth_nonpass_after_repair | 0 |
| post_render failed | <=2/20 |
| canonical unique hooks engaged | >=3 |
| longest no-motif streak | <=3 |
| avg wall time | <=25s |

**Deliverables:**
- `docs/reports/reportVer0.7.2.1.md` (metrics must come from `analyze_agentic_run.py --json` output)
- `docs/plans/planVer0.7.2.1.md` (this file, formally archived)

---

## File Impact Summary

### Modified
```text
metarpg/agentic/director_agent.py          # +target->destination normalize; +structure validation
metarpg/agentic/transaction_validator.py   # +move_player missing destination hard_fail
metarpg/agentic/committer.py               # +raise on invalid move (defensive)
metarpg/agentic/semantic_judge.py          # +hook_id: str|None in SemanticJudgment
metarpg/agentic/hook_manager.py            # use hook_id not category; whitelist guard
metarpg/agentic/post_render_checker.py     # status: pass/repaired/failed
metarpg/agentic/runner.py                  # +L2 reject gating (failed status)
scripts/agentic_dungeon_smoke_test.py      # +three-state tracking; +unrepaired_reject tracking
```

### New
```text
scripts/analyze_agentic_run.py             # artifact -> metrics, --json, --fail-on-invariant
tests/test_move_player_schema.py
tests/test_hook_id_integrity.py
tests/test_absence_response_targeted.py
docs/reports/reportVer0.7.2.1.md
docs/plans/planVer0.7.2.1.md
```

## Explicitly Out of Scope

- No new hooks/hints/motifs added
- No NPC follow logic to mask absence_response issues
- No repaired/failed counted as pass
- No new SemanticJudge functions
- No Turn 11/19 absence behavior analysis before move no-op fix
