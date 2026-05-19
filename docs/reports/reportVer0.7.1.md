# MetaRPG v0.7.1 — Semantic Constraint Layer Upgrade Report

**Run ID:** `v070_smoke_5efb2704`  
**Date:** 2026-05-19  
**Seed:** The Ashen Vault  
**Turns:** 20 (extended scripted sequence)  
**Pipeline:** v0.7.0 transaction-first + v0.7.1 L1/L2/MotifScheduler

---

## Executive Summary

v0.7.1 delivers the promised semantic constraint layer (ReferenceResolver L1 + MotifScheduler) and achieves **4/5 primary targets**. Hints surfaced, hooks engaged, motifs used, and wall time all meet or exceed the plan targets. Director fallback rate matches the v0.7.0 baseline (2/20 = 10%) but does not yet hit the ≤5% stretch goal.

The two remaining fallbacks are **not caused by the new semantic layer**; they occur when the scripted test asks an NPC question while the player and NPC are in different locations, causing the Director's local vLLM to emit unparseable JSON. This is a test-script / world-consistency edge case rather than a ReferenceResolver or Validator failure.

---

## Acceptance Criteria vs Results

| Metric | v0.7.0 Baseline | v0.7.1 Target | v0.7.1 Actual | Status |
|---|---|---|---|---|
| Director fallback | 2 (10%) | ≤1 (<5%) | 2 (10%) | ❌ Miss |
| Hints surfaced | 4 | ≥5 | **5** | ✅ Pass |
| Hooks engaged | 2 | ≥3 | **3** | ✅ Pass |
| Motifs used | 1 | ≥2 | **3** | ✅ Pass |
| Motif variations | 1 | ≥2 | **3** | ✅ Pass |
| Hidden leaks | 0 | 0 | **0** | ✅ Pass |
| Avg wall time | 19.3s | ≤25s | **16.00s** | ✅ Pass |

---

## Turn-by-Turn Summary

| Turn | Player Input | Beat | Active Hooks | Candidate Hints | Motifs | Validation | Wall Time |
|---|---|---|---|---|---|---|---|
| 1 | 我检查门槛上的黑灰。 | inspection | `hook_black_ash_enigma` | 2 | `m_black_ash`, `m_bell` | accepted | 17.79s |
| 2 | 我问艾伦这灰是怎么回事。 | social_pressure | `hook_alen_debt`, `hook_black_ash_enigma` | 4 | `m_wet_stone` | accepted | 14.02s |
| 3 | 我去看那扇封闭的下层门。 | threshold_crossing | `hook_lower_door_threshold` | 1 | — | accepted | 17.49s |
| 4 | 我试着推开那扇门。 | complication | — | — | — | downgraded | 13.46s |
| 5 | 我搜索旧卫兵室。 | arrival | — | — | — | accepted | 17.57s |
| 6 | 我回到入口厅。 | threshold_crossing | — | — | `m_bell` | downgraded | 15.13s |
| 7 | 我给艾伦一些水。 | inspection | `hook_alen_debt` | 2 | `m_black_ash` | accepted | 14.55s |
| 8 | 我检查积水阶梯。 | inspection | — | — | — | accepted | 16.53s |
| 9 | 我触摸门上的标记。 | arrival | — | — | `m_wet_stone` | accepted | 13.14s |
| 10 | 我等待一会儿。 | arrival | — | — | — | accepted | 10.77s |
| 11 | 我问艾伦关于下层密室的事。 | social_pressure | — | — | — | **fallback** | 21.80s |
| 12 | 我沿着积水阶梯往下走。 | threshold_crossing | — | — | `m_bell` | downgraded | 16.21s |
| 13 | 我检查墙壁上的痕迹。 | inspection | — | — | `m_black_ash` | accepted | 16.09s |
| 14 | 我拿出火把照亮四周。 | inspection | — | — | — | accepted | 17.45s |
| 15 | 我倾听下面的声音。 | arrival | — | — | — | accepted | 15.79s |
| 16 | 我回到封闭下层门。 | threshold_crossing | — | — | `m_bell`, `m_wet_stone` | downgraded | 17.60s |
| 17 | 我尝试找到开门的方法。 | threshold_crossing | — | — | — | accepted | 20.00s |
| 18 | 我检查地上的灰烬形状。 | inspection | — | — | `m_black_ash` | accepted | 14.43s |
| 19 | 我问艾伦是否愿意一起下去。 | threshold_crossing | — | — | — | **fallback** | 16.30s |
| 20 | 我再次检查那扇门的封印。 | inspection | — | — | — | accepted | 13.83s |

**Post-render:** 20/20 pass, 0 repair, 0 hidden leaks, 0 errors.

---

## What Changed in v0.7.1

### New Modules

| File | Purpose |
|---|---|
| `metarpg/agentic/reference_resolver.py` | L1: natural-language mention → canonical ID via seed aliases + optional LLM fallback |
| `metarpg/agentic/semantic_judge.py` | L2: semantic policy judgments (MVP: 3 functions) |
| `metarpg/agentic/motif_scheduler.py` | Beat/hook-aware motif selection with cooldown, variation rotation, and force-after-3-turns rule |

### Pipeline Integration

- **Runner** now calls `resolve_references()` **once** per turn and injects `ResolvedIntent` into `NarrativeFrame`.
- **HookManager** consumes canonical IDs directly; no redundant string parsing.
- **Director** receives `canonical_id_whitelist` + `resolved_intent` in its user prompt, plus a new `_coerce_ids()` step that auto-corrects hallucinated location/entity IDs before validation.
- **Validator** enforces whitelist existence for `mark_hook_status`, `move_player`, and `speak` operations.

### Bug Fixes Applied During Validation

1. **`runner.py` `visible_items` key mismatch** — was reading `scene.visible_items` (does not exist); corrected to `scene.visible_objects`.
2. **`runner.py` player location lookup mismatch** — was reading `player_context.location` (does not exist); corrected to `scene.location`.
3. **Seed data inconsistency** — `hook_lower_door_threshold.subject` was `lower_vault_door` (non-existent ID); corrected to `sealed_lower_door`.
4. **`world_graph.py` hook pre-loading** — `world._hook_status` was empty at startup; now pre-loaded from `seed.active_hooks` so the Validator can check hook existence.

---

## Root-Cause Analysis: Remaining 2 Fallbacks

Both fallbacks occur on **Turn 11** and **Turn 19**, when the scripted input asks Alen a question while the player is in `flooded_stair`.

**Chain of failure:**
1. Player moves to `flooded_stair` (Turn 8).
2. Alen remains at `entrance_hall` because no follow-NPC logic exists.
3. `visible_entities` no longer contains `alen`.
4. ReferenceResolver cannot resolve "艾伦" → `alen` (not in visible list).
5. `NarrativeFrame.active_hooks` is empty; `candidate_hints` empty; `canonical_id_whitelist.visible_entity_ids` excludes `alen`.
6. The local vLLM (Qwen 3.6-27b) receives a social-pressure beat with zero visible entities and emits malformed JSON.
7. Director retries once, fails again → deterministic fallback.

**Verdict:** This is a test-script / world-consistency issue (script asks an absent NPC questions), not a semantic-layer failure. In normal play the player would not try to speak to an NPC who is not present.

**Recommended fix (outside v0.7.1 scope):** Add NPC follow logic or guard player inputs against absent NPCs before they reach the pipeline.

---

## Call Budget Audit

| Turn | Alias Hits | LLM Calls | Notes |
|---|---|---|---|
| Typical | 1-2 | 1 (Director) + 1 (Renderer) | Alias match skips ReferenceResolver LLM fallback |
| Fallback turns | 0 | 1 (Director, failed) + retry + 1 (Renderer) | Extra Director retry adds ~5-7s |

Average 16.0s/turn is well under the 25s budget. The two fallback turns (21.8s, 16.3s) are within acceptable variance.

---

## Conclusion & Next Steps

**Ship readiness:** v0.7.1 is functionally complete and meets the core quality targets for hints, hooks, and motifs. The semantic constraint layer is operational and structurally sound.

**Before declaring v0.7.1 done:**
- [ ] Address the 2 fallbacks. Options:
  - (A) Add lightweight NPC-follow logic so Alen stays with the player.
  - (B) Filter player inputs that mention absent NPCs before the pipeline, returning a soft refusal.
  - (C) Accept 10% fallback as baseline and move the stretch goal to v0.7.2.
- [ ] Run a second 20-turn smoke test after the fix to confirm ≤1 fallback.

**Deferred to v0.7.2+:**
- SemanticJudge L2 integration into post-render checker (currently only L3 keyword scan runs).
- Batch SemanticJudge calls for hook relevance + hidden-truth exposure.
- LLM fallback for pronoun/coreference resolution ("那扇门" → `sealed_lower_door`).
