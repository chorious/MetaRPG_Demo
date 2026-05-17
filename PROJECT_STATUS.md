# MetaRPG Project Status

Last updated: 2026-05-18

## Active Track

**v0.6 agentic Python pipeline**

The current main development line is the LLM-first agentic narrative loop:

```text
StoryPacket → Writer → Translator → Scanner → Hard Auditor → Soft Auditor → Editor → Committer
```

Goal: make the player face story, not code. Let LLM interpret/write, let code ground/commit.

Primary eval: **Greyfen 5-turn beer loop**

---

## Baseline

**v0.1–v0.5 deterministic legacy engine**

Stable baseline for regression comparison. Contains parser, meta-act, proposer, assembler, old turn loop, CLI, session logger.

Do not expand with new proposer heuristics or behavior categories unless needed for legacy regression.

---

## Paused

**UPF bridge**

Python JSON bridge, session adapter, UPF protocol, snapshot export.

Do not resume until the agentic Python loop passes primary eval.

---

## Freeze Rules (until primary eval is stable)

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
Schema stabilization
Eval runner fixes
Story packet continuity
Auditor rule refinement
Scorecard correctness
Document moves
Small compatibility wrappers
```

---

## Directory Guide

| Path | Purpose |
|------|---------|
| `metarpg/agentic/` | v0.6 main pipeline |
| `metarpg/models.py` | Core world data structures (shared) |
| `metarpg/engine.py` | Legacy deterministic engine |
| `scripts/play_agentic.py` | Interactive CLI |
| `scripts/agentic_5turn_smoke_test.py` | Automated eval |
| `docs/plans/` | Design plans |
| `docs/reviews/` | Post-hoc critiques |
| `docs/prompts/` | Prompt references |
| `docs/architecture/` | Stable interface docs |
| `docs/archive/` | Old plans and reviews |
| `runtime/agentic_runs/` | Turn artifacts, scorecards, summaries |
| `evals/cases/` | Eval case definitions |
