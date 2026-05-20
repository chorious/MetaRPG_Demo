# MetaRPG v0.7.5 Review

Date: 2026-05-20

Reviewed commit: `c2f73ea` - `MetaRPG v0.7.5 - Semantic Coverage Closure + Play Experience Gates`

Scope:

- `reports/v0.7.5_patch_report.md`
- `metarpg/agentic/post_render_checker.py`
- `metarpg/agentic/semantic_judge.py`
- `metarpg/agentic/transaction_validator.py`
- `metarpg/agentic/runner.py`
- `metarpg/agentic/play_cli.py`
- `scripts/analyze_agentic_run.py`
- `scripts/analyze_play_run.py`
- `tests/test_v075_*.py`

## Executive Summary

v0.7.5 closes several important correctness gaps around unreachable targets, absent NPCs, object-as-entity errors, object personification, hidden truth exposure, and play experience gates.

The patch is directionally right and the reported unit suites pass. However, this review does not consider v0.7.5 fully closed yet. Three issues weaken the reliability of the correctness claim:

1. Required L2 checks still fail open when the LLM call or JSON parsing fails.
2. The play analyzer does not consume the semantic data emitted by the real play CLI artifact format.
3. The analyzer's `l2_required` reconstruction is not equivalent to production `_is_l2_required()`.

There is also one medium-risk compatibility regression in `validate_transaction()` around missing whitelists.

## Findings

### High - Required L2 checks fail open on judge call failure

Files:

- `metarpg/agentic/semantic_judge.py:389`
- `metarpg/agentic/semantic_judge.py:296`
- `metarpg/agentic/post_render_checker.py:172`

`post_render_checker.check_rendered_prose()` is designed to fail closed when `l2_required=True`: if no client is available, it returns `status="failed"`, and the surrounding `try/except` also intends to fail the turn if L2 execution fails.

The implementation does not fully uphold that contract. `_call_judge()` catches every exception from `client.chat_json()` and returns `[]`:

```python
try:
    raw = client.chat_json(messages, temperature=0.2)
except Exception:
    return []
```

Each single-judgment wrapper then turns an empty result into a permissive pass with `category="parse_error"`. For example, `judge_intent_fulfillment()` returns:

```python
SemanticJudgment(
    verdict="pass",
    category="parse_error",
    evidence="Judge returned no results",
    ...
)
```

That means an L2-required turn can pass if the local vLLM times out, returns malformed JSON, or raises a connection error. The fail-closed branch in `post_render_checker.py` never sees the exception.

Impact:

- Hidden truth exposure can pass when the judge is down.
- Unreachable-response contradictions can pass when judge output is malformed.
- Object personification can pass when judge parsing fails.
- `l2_required_but_not_run_count=0` can be misleading, because the system records a semantic judgment even when the actual judge failed.

Recommendation:

- For required L2 calls, propagate exceptions from `_call_judge()` or return an explicit `verdict="reject"` / `category="judge_error"`.
- If permissive fallback is still needed for non-required optional checks, add a `fail_closed: bool` parameter or a separate strict helper.
- Add a regression test where a mock client raises from `chat_json()` and `check_rendered_prose()` must return `status="failed"` on an L2-required transaction.

### High - Play analyzer and real play artifacts are disconnected

Files:

- `metarpg/agentic/play_cli.py:328`
- `scripts/analyze_play_run.py:25`
- `scripts/analyze_play_run.py:71`

`scripts/analyze_play_run.py` expects v0.7 semantic judgments in this shape:

```python
turn["post_render"]["semantic_judgments"]
```

It also expects hidden truths and public facts from fields such as:

```python
turn["story_packet"]["auditor_only"]["hidden_truths"]
turn["admitted_patch"]
turn["story_packet"]["player_context"]["known_facts"]
```

The real v0.7 play CLI persists a much lighter `turn_NNN.json`:

```python
{
    "post_render_status": ...,
    "post_render_issues": ...,
    "assumptions": ...,
    "operations": ...
}
```

It does not persist nested `post_render`, `semantic_judgments`, `story_packet`, or public patch data into the monolithic play turn file.

Impact:

- `perspective_shift_count` can false-negative because semantic judgments are not found.
- `hidden_truth_semantic_reveal_count` can false-negative for the same reason.
- `hidden_public_fact_overlap_count` can false-negative because hidden truths and public facts are not present in the play turn artifact.
- The v0.7.5 play gates can report zero violations without actually observing the required evidence.

Recommendation:

- Either update `_persist_v070_turn()` to write the full `post_render` object, semantic judgments, story packet, and public patch data, or update `analyze_play_run.py` to read the split `artifact_NNN_post_render.json` and related artifacts from `RunLogger`.
- Add an integration test that writes artifacts in the exact shape produced by `play_cli.py`, not only synthetic fixtures.

### Medium - Analyzer `l2_required` is not equivalent to production

Files:

- `scripts/analyze_agentic_run.py:91`
- `metarpg/agentic/post_render_checker.py:206`

Production `_is_l2_required()` currently checks nine conditions:

- terminal hook status changes
- canon commitments
- forbidden claims
- obligation-bearing response modes
- `must_not_claim`
- `speak` / `observe_reaction`
- resolved target `available=false`
- candidate hints matching symbolic risk patterns
- backward-compatible assumption sources

The analyzer reconstructs only a subset from artifacts. It does not appear to include the full production matrix, especially response-mode obligations, `must_not_claim`, unavailable target dictionaries, and candidate-hint symbolic risk.

Impact:

- `l2_required_but_not_run_count` can be falsely low.
- v0.7.5 report metrics can claim L2 coverage closure even if production would require L2 on turns the analyzer does not classify as required.

Recommendation:

- Prefer serializing the production `l2_required` decision into artifacts at runtime.
- Alternatively, factor `_is_l2_required()` into a pure helper whose inputs can be reconstructed, and reuse the same helper from the analyzer.
- Add a test that creates an artifact with `must_not_claim` or symbolic-risk candidate hints and verifies analyzer coverage.

### Medium - Missing whitelist now behaves like explicit empty whitelist

Files:

- `metarpg/agentic/transaction_validator.py:49`
- `metarpg/agentic/transaction_validator.py:117`

The v0.7.5 fix correctly distinguishes `[]` from `None` for visible entity lists, but `validate_transaction()` now normalizes a missing whitelist to an empty list:

```python
if visible_entity_ids is None:
    visible_entity_ids = []
```

Then `_entity_visible()` treats any non-`None` list as authoritative:

```python
if visible_entity_ids is not None:
    return entity in visible_entity_ids
```

This means a caller that does not populate `canonical_id_whitelist` no longer falls back to `_entity_present(entity, world)`. It behaves as if the scene explicitly has no visible entities.

Impact:

- Direct validator callers can reject valid `speak` / `observe_reaction` operations against NPCs present in `WorldState`.
- Legacy or test paths that build a bare `TurnTransaction` without a frame whitelist may become stricter than intended.
- The fix for the `None` vs `[]` trap is correct in principle, but the call-site normalization loses the semantic difference between missing and explicitly empty.

Recommendation:

- Preserve `None` when the whitelist key is absent.
- Treat an explicit key with value `[]` as authoritative "nothing visible".
- Add tests for both cases:
  - no `canonical_id_whitelist` -> fallback to world presence
  - `visible_entity_ids=[]` -> reject non-player/non-environment entities

## Test Gaps

The targeted v0.7.5 tests are useful but do not prove the main LLM-backed rejection paths.

Examples:

- `tests/test_v075_object_personification.py` verifies the fixture and no-client pass behavior, but not a mock-client reject through `check_rendered_prose()`.
- `tests/test_v075_unreachable_repair.py` verifies the fixture and no-client pass behavior, but not the required-turn reject path with a mock judge response.
- There is no regression test for judge timeout / malformed JSON causing `status="failed"` on L2-required turns.
- There is no test using the exact `play_cli.py` artifact shape to prove `analyze_play_run.py` sees semantic judgments and hidden-public overlap.

Recommended additions:

1. Mock `chat_json()` raising an exception on an L2-required turn. Expected: `check_rendered_prose()` returns `failed`.
2. Mock object personification judge returning `reject`. Expected: `check_rendered_prose()` returns `failed`.
3. Persist one real-shape play turn via `_persist_v070_turn()` and run `analyze_play_run()`. Expected: semantic gates consume the emitted evidence.
4. Analyzer fixture for each production `_is_l2_required()` condition.

## Performance Review

The reported latency regression is real and explained by the current implementation.

`post_render_checker.py` runs up to four serial judge calls per L2-required turn:

1. `judge_hidden_truth_exposure`
2. `judge_render_claim_support`
3. `judge_intent_fulfillment`
4. `judge_object_personification`

The repair loop in `runner.py` re-runs the full checker after repair, so a failed render can double that cost.

Recommended order:

1. Fix fail-closed semantics before optimizing.
2. Parallelize independent judge calls with the existing `parallel_dispatch.py`, if the local vLLM server can handle concurrency.
3. Make repair re-check selective where possible.
4. Only then shrink the L2 trigger matrix, because the current broad matrix is compensating for correctness gaps.

## Verification

Commands run against current HEAD:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_v075_unreachable_repair.py tests/test_v075_object_personification.py tests/test_v075_play_analyzer.py -q
```

Result:

```text
9 passed
```

```powershell
python -B -m pytest -p no:cacheprovider tests/ -k "agentic or render or semantic or play or analyzer" --tb=short -q
```

Result:

```text
94 passed
```

Note: the passing tests do not cover the fail-open judge-error path or the real play artifact/analyzer mismatch described above.

## Review Verdict

v0.7.5 is a strong correctness patch, but it should not be treated as fully closed until the analyzer/artifact contract and L2 fail-closed semantics are fixed.

Recommended next patch:

1. Make required L2 judge failure produce `status="failed"`.
2. Align play artifact persistence with `analyze_play_run.py`.
3. Align analyzer `l2_required` with production `_is_l2_required()`.
4. Restore missing-whitelist fallback behavior in `transaction_validator.py`.
5. Re-run targeted tests, analyzer tests, 20-turn Ashen Vault smoke, and 5-turn Greyfen play.
