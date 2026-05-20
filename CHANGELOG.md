# Changelog

Version milestones for MetaRPG_Dev. Latest is **v0.7.5**.

---

## v0.7.5 — 2026-05-20

**Semantic Coverage Closure + Play Experience Gates.** Correctness-only patch; no structural refactor, no new gameplay.

- `scripts/analyze_play_run.py` — complete rewrite: deep semantic-judgment reading, cross-turn state continuity tracking, hidden/public fact overlap detection, diagnostic code output (`METARPG_*`)
- `scripts/analyze_agentic_run.py` — added `object_as_visible_entity_count`, `object_personification_claim_count`, `unreachable_response_contradiction_count`
- `post_render_checker.py` — expanded `_is_risk_turn` → `_is_l2_required` (9 conditions); fail-closed if L2 required but client unavailable; added `judge_object_personification` call
- `semantic_judge.py` — new `judge_object_personification()`; enhanced `judge_intent_fulfillment` with `must_not_claim` enforcement and unreachable hard rule
- `transaction_validator.py` — fixed `_entity_visible()` `None` vs `[]` bug; added `object_as_entity` / `object_as_entity_reaction` hard_fail
- `director_agent.py` — `_validate_structure` rejects `speak`/`observe_reaction` on objects
- `renderer_agent.py` — system prompt BAD/GOOD few-shots for object personification and unreachable response
- `runner.py` — ensures `visible_entity_ids` / `visible_objects` never `None`; passes `render_brief` / `resolved_intent` to checker
- New fixtures: `bad_prose_*.json` (4), `bad_play_*.json` (2)
- New tests: `test_v075_unreachable_repair.py`, `test_v075_object_personification.py`, `test_v075_play_analyzer.py` (9 targeted tests total)
- **Known issue:** turn wall time regressed from ~20s to ~40s due to serial L2 judge calls (to be addressed in v0.7.6 or via hotfix)

## v0.7.4 — 2026-05-19

**Intent Fulfillment & Current-Turn Render Contract.** (`a1978aa`)

- `semantic_judge.py` — new `judge_intent_fulfillment()` (L2): checks prose against player input, resolved intent, and current-turn obligation
- `render_brief.py` — added `current_turn_obligation` (response_mode, must_not_claim, grounding_scope)
- `renderer_agent.py` — consumes `current_turn_obligation` in system prompt
- `post_render_checker.py` — integrated intent_fulfillment into L2 block
- `runner.py` — passes `render_brief` to renderer and checker
- Tests: `test_render_brief_grounding` expanded

## v0.7.3 — 2026-05-19

**Semantic Quality Closure.** (`0210abc`)

- Repair loop: one-shot render repair via DeepSeek Flash on post-render failure, with re-check
- `semantic_judge.py` — `judge_render_claim_support` now aware of entity/object type discipline
- `post_render_checker.py` — L3 keyword scan + L2 semantic judge layering finalized
- Smoke test: 20-turn Ashen Vault validation

## v0.7.2 — 2026-05-19

**Semantic Layer Completion.** (`9eb2981`)

- `semantic_judge.py` — 3-judge suite: `judge_hook_relevance`, `judge_hidden_truth_exposure`, `judge_render_claim_support`
- `post_render_checker.py` — L2 semantic judge integration (risk-turn only)
- `analyze_agentic_run.py` — metrics framework for semantic runs

## v0.7.1 — 2026-05-19

**L2 Semantic Judge MVP.**

- Local vLLM integration (`192.168.50.20:8101`, `qwen3.6-27b-nvfp4`) for semantic boundary checks
- `judge_hidden_truth_exposure`, `judge_render_claim_support` initial implementation
- Model routing: DeepSeek Flash → Renderer; Local vLLM → Director / Feasibility / SemanticJudge

## v0.7.0 — 2026-05-19

**Transaction-first pipeline.** Major architecture rewrite from legacy 12-step engine to agentic LLM pipeline.

- New pipeline: Narrative Grammar → NarrativeFrame → Director → Validator → Committer → Renderer → Post-render Checker
- `TurnTransaction`, `NarrativeFrame`, `RenderBrief`, `ValidationResult` dataclasses
- L0/L1/L2/L3 constraint layers: deterministic hard constraints, reference resolution, semantic policy judge, hygiene scan
- `agentic/` package: `director_agent`, `transaction_validator`, `committer`, `renderer_agent`, `post_render_checker`, `semantic_judge`, `render_repair`, `render_brief`, `feasibility`, `runner`
- `scripts/play_agentic.py` — interactive CLI entry point
- `scripts/agentic_dungeon_smoke_test.py` — automated smoke harness

---

## v0.6.6.1 — 2026-05-18

Hotfix on top of v0.6.6: 5 engineering breakpoints + `inner_monologue`.

- Touched: `committer`, `crystallize`, `hard_auditor`, `lore_conflict`, `refusal_fallback`, `runner`, `story_packet`, `writer_agent`
- Tests updated: `test_crystallize`, `test_lore_conflict`, `test_refusal_fallback`
- Docs: `docs/diary/2026-05-18.md`, `docs/reviews/reviewVer0.6.6.1.md`
- Commit `902c8a6`

## v0.6.6 — 2026-05-18

Three-stage release: Bold-first / Safe fallback pipeline + six narrative primitives.

### Step 0+1 — Bold-first + Safe fallback pipeline (`9a719a1`)

- New modules: `feasibility.py`, `parallel_dispatch.py`, `refusal_fallback.py`
- Major rewrite of `agentic/runner.py` (+513 lines)
- Expanded `writer_agent` with multiple modes
- New eval cases: `absent_npc_talk`, `ambient_guests_pass`, `lightsaber_absence`, `notebook_medium_issue`, `npc_offer_needs_patch`
- New tests: `test_feasibility`, `test_model_client_thinking`, `test_parallel_dispatch`, `test_recent_events_consume`, `test_refusal_fallback`, `test_v064_regression`, `test_writer_modes`
- Planning/review docs for v0.6.4 / v0.6.5 / v0.6.6 added retroactively

### Primitives A+B — time_flow + entity_lifecycle (`bd2fa8a`)

- New: `agentic/time_flow.py`, `agentic/entity_lifecycle.py`
- `models.py` extended
- Wired into `committer`, `runner`, `story_packet`, `writer_agent`
- Tests: `test_time_flow`, `test_entity_lifecycle`

### Primitives C–F — crystallize + belief_tracker + lore_conflict + offscreen_tick (`7bf4e98`)

- New: `agentic/crystallize.py`, `agentic/belief_tracker.py`, `agentic/lore_conflict.py`, `agentic/offscreen_tick.py`
- Tests: `test_belief_collapse`, `test_crystallize`, `test_lore_conflict`, `test_offscreen_tick`

## v0.6.3 — 2026-05-18

Canonical runner + CLI entry point + artifact authority. Two commits.

- **`84189d0` (main)** — new `agentic/runner.py` (239 lines), `agentic/play_cli.py` (189), `agentic/run_logger.py` (38); `scripts/play_agentic.py` shrunk from 367 → minimal shim; smoke test refactored
- **`b244abb` (review fixes)** — forensic correctness, JSON stability, auditor alignment; `play_cli`, `writer_agent`, `soft_auditor_agent` patched; `test_v063_regression` added (426 lines)

Note: commit `4929fea` ("Architecture reorg: docs, run artifacts, and interface docs") sits between v0.6.1 and v0.6.3 with no version bump — pure reshuffle.

## v0.6.1 — 2026-05-18

First **agentic LLM pipeline** release. Establishes the eight-stage architecture:

```
StoryPacket → Writer → Translator → Scanner → Hard Auditor → Soft Auditor → Editor → Committer
```

- 29 new files, +7192 lines
- New `metarpg/agentic/` package: `committer`, `editor_agent`, `eval_runner`, `hard_auditor`, `model_client`, `repair_loop`, `scanner`, `schemas`, `scorecard`, `soft_auditor_agent`, `story_packet`, `teacher_agent`, `translator_agent`, `writer_agent`
- New eval `evals/cases/greyfen_beer_loop.json` (primary eval going forward)
- New interactive CLI `scripts/play_agentic.py` (later canonicalized in v0.6.3)
- `test_v061_regression` baseline
- Commit `4206195`

## v0.5.2 — 2026-05-18 (baseline)

**Legacy deterministic engine** with authoritative UPF bridge. Initial public commit: 72 files, +17 108 lines.

- Parser, meta-act, proposer, assembler, 12-step turn loop, CLI, session logger
- Scenario hooks + Greyfen scenario
- UPF bridge protocol, session, snapshot export
- Chinese test suite + Chinese script `milestone_zh.txt`
- Archived plans: `planVer0.1.md` … `planVer0.5.1-playable-upf-bridge.md`
- Commit `8c1312e`

**Status:** frozen as regression baseline. Do not extend with new proposer heuristics or behavior categories unless required for legacy regression. See `PROJECT_STATUS.md`.

---

## Skipped version numbers

`v0.6.0`, `v0.6.2`, `v0.6.4`, `v0.6.5` were never tagged as code releases:

- `v0.6.4` / `v0.6.5` — planning, report, and review docs exist (`planVer0.6.4.md`, `reportVer0.6.4.md`, `reportVer0.6.5.md`, `reviewVer0.6.4.md`, `reviewVer0.6.5.md`); the corresponding code shipped inside v0.6.6 Step 0+1
- `v0.6.0`, `v0.6.2` — no artifacts; appear to have been internal placeholders

---

## Active vs. paused tracks

| Track | Status | Version |
|---|---|---|
| Agentic Python pipeline | **Active** | v0.7.5 |
| Legacy deterministic engine | Frozen baseline | v0.5.2 |
| UPF bridge | Paused until agentic passes primary eval | v0.5.2 |

Primary eval: Greyfen 5-turn beer loop. Freeze rules in `PROJECT_STATUS.md`.
