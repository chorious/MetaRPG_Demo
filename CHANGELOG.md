# Changelog

Version milestones for MetaRPG_Dev. All commits below landed on **2026-05-18** as a single bundled push; dates therefore reflect commit dates, not development span. Latest is **v0.6.6.1**.

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
| Agentic Python pipeline | **Active** | v0.6.6.1 |
| Legacy deterministic engine | Frozen baseline | v0.5.2 |
| UPF bridge | Paused until agentic passes primary eval | v0.5.2 |

Primary eval: Greyfen 5-turn beer loop. Freeze rules in `PROJECT_STATUS.md`.
