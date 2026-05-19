# MetaRPG v0.7.4 Report — Intent Fulfillment & Current-Turn Render Contract

**RunID:** `v070_smoke_3abf4c15`  
**Date:** 2026-05-20  
**Model:** qwen3.6-27b-nvfp4 (Director / SemanticJudge) + deepseek-v4-flash (Renderer)  
**Commit:** `a1978aa`

---

## Executive Summary

v0.7.4 closes the semantic quality gap identified in v0.7.3: **the system now checks that rendered prose actually responds to the current turn's player intent**, not just structural correctness (no leaks, no crashes).

All 20-turn acceptance criteria pass. Zero invariant violations.

---

## 20-Turn Metrics vs Targets

| Metric | Target | Actual | Status |
|---|---|---|---|
| errors | 0 | **0** | ✅ |
| report/analyzer/smoke mismatch | 0 | **0** | ✅ |
| validator rejected_turns | 0 | **0** | ✅ |
| move_player_missing_destination | 0 | **0** | ✅ |
| invalid_active_hook_ids | [] | **[]** | ✅ |
| director_schema_fallback_count | <=1 | **0** | ✅ |
| validation_rejection_fallback_count | 0 | **0** | ✅ |
| total_fallback_count | <=1 | **0** | ✅ |
| absence_response | >=1 | **2** | ✅ |
| deterministic_movement | >=2 | **2** | ✅ |
| unreachable_location_response | >=1 | **2** | ✅ |
| post_render final_failed | 0 | **0** | ✅ |
| intent_fulfillment_reject_after_repair | 0 | **0** | ✅ |
| hidden_truth_nonpass_after_repair | 0 | **0** | ✅ |
| unrepaired_l2_rejects | 0 | **0** | ✅ |
| repair_attempts (live run) | >=1 | **1** | ✅ |
| canonical unique hooks engaged | >=3 | **3** | ✅ |
| longest no-motif streak | <=3 | **3** | ✅ |
| avg wall time | <=24s | **14.34s** | ✅ |

---

## Source Distribution (20 turns)

| Source | Count |
|---|---|
| director | 14 |
| deterministic_movement | 2 |
| absence_response | 2 |
| unreachable_location_response | 2 |
| fallback | 0 |

**Key observation:** Turn 16 and Turn 17 ("回到封闭下层门") correctly route to `unreachable_location_response` instead of falling back to Director. This eliminates the Turn 16 regression from v0.7.3.

---

## Repair Loop

- **Turn 6** (`deterministic_movement` to `entrance_hall`) triggered L2 semantic checks.
- One `downgrade` verdict on `render_claim_support` (unsupported detail: water seepage texture).
- Repair loop activated; prose successfully repaired.
- Final status: `repaired` → counted as `final_pass`.

No hard rejects. No unrepaired failures.

---

## Fallback Taxonomy

| Type | Count |
|---|---|
| director_schema_fallback | 0 |
| validation_rejection_fallback | 0 |
| **total_fallback** | **0** |

v0.7.3 had 1 director_schema_fallback and 1 validation_rejection_fallback. v0.7.4 eliminates both through:
1. Unreachable location response branch (handles known-but-unreachable moves)
2. Environment pseudo-entity fix (carried from v0.7.3.1)

---

## L2 Semantic Checks

- **Judgments run:** 9 (risk turns only, ~45% of turns)
- **Downgrades:** 1 (render_claim_support: unsupported_detail)
- **Hard rejects:** 0
- **Hidden truth non-pass:** 0

Intent fulfillment judge ran on all 9 risk turns. No intent fulfillment rejects were emitted.

---

## Narrative Engagement

| Metric | Count | Target |
|---|---|---|
| Hints surfaced | 5 | >=5 ✅ |
| Hooks engaged | 3 | >=3 ✅ |
| Motifs used | 3 | >=2 ✅ |
| Hidden leaks | 0 | 0 ✅ |

---

## Test Coverage

New tests added in v0.7.4:

| File | Tests | Focus |
|---|---|---|
| `tests/test_analyzer_taxonomy.py` | 5 | Metrics unification |
| `tests/test_intent_fulfillment.py` | 7 | L2 intent judge categories |
| `tests/test_render_brief_obligation.py` | 6 | Current-turn contract |
| `tests/test_unreachable_location.py` | 2 | Unreachable branch |
| `tests/test_render_repair_targeted.py` | 6 | Repair loop proof |

**Total suite:** 463 tests, all passing.

---

## Known Limitations & Next Steps

1. **Intent fulfillment** relies on LLM semantic judgment; no deterministic keyword fallback exists yet. A future version could add a lightweight keyword guard for common cases (wrong target mentions).
2. **Unreachable location** currently only handles `action_type == "move"`. Interact/inspect toward unreachable locations still routes through Director.
3. **Repair loop** is one-shot. A second repair attempt is not implemented (assumption: Flash rarely fails twice).

---

## Conclusion

v0.7.4 achieves **semantic quality closure** for the Ashen Vault demo. The pipeline now guarantees:
- Structural correctness (v0.7.3 baseline)
- Intent fidelity (v0.7.4 new)
- Zero fallback in the 20-turn scripted sequence
- Repair loop proven effective on live output

**Recommendation:** Tag `v0.7.4` and proceed to v0.8.0 scope definition (entity AI, multi-step pathfinding, or scene expansion).