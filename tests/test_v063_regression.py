"""v0.6.3 regression cases — deterministic, no LLM required.

Covers reviewVer0.6.3.md fixes:
- P0: runner captures raw_text on Writer failure
- P0: RunLogger writes manifest + events + errors + summary
- P1: Writer JSON repair prompt template
- P2: Hard Auditor treats empty-inventory prop usage as medium_issue
- P3: Scorecard truthfulness (soft cap 0.85, missing output → 0.0)
- P3: Live play and eval both use canonical runner contract
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import run_agentic_turn
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    NarrativeClaim,
    Segment,
    TurnDraft,
    WriterOutput,
)
from metarpg.agentic.writer_agent import WriterOutputError
from metarpg.models import Fact, WorldState
from metarpg.scenarios.greyfen import build


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_world() -> WorldState:
    w = WorldState()
    w.locations = {"greyfen_tavern"}
    w.npcs = {"mara"}
    w.facts.add(Fact("at", ("player", "greyfen_tavern")))
    w.facts.add(Fact("at", ("mara", "greyfen_tavern")))
    return w


def _story_packet() -> dict:
    return {
        "scene": {
            "location": "greyfen_tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": [],
            "atmosphere": "tense greyfen_tavern (tavern, drink)",
        },
        "player_context": {
            "known_facts": [],
            "recent_events": [],
            "inventory_or_handheld": [],
        },
        "npc_surface": {
            "mara": {
                "role": "barkeep",
                "visible_mood": ["neutral"],
                "can_speak": True,
                "_auditor_relations": {},
            }
        },
        "allowed_effect_kinds": [
            "transient_event",
            "journal_note",
            "observe_reaction",
            "relation_delta",
            "consume_item",
            "acquire_item",
            "knowledge_transfer",
            "reveal",
        ],
        "allowed_reveals": [],
        "forbidden": {
            "entities_not_present": ["rusk", "iven"],
            "hidden_fact_aliases": ["mara_at_old_mine", "secret_smuggling_ring"],
            "forbidden_narration": [
                "npc_inner_thought_hidden_fact",
                "remote_action",
                "raw_event_id",
                "belief_probability",
            ],
        },
    }


# ---------------------------------------------------------------------------
# P0: Runner raw_text capture
# ---------------------------------------------------------------------------

def test_runner_captures_raw_text_on_writer_failure(tmp_path: Path) -> None:
    """When run_writer raises WriterOutputError with raw_text, runner must
    capture it into the error turn record."""
    world = build()
    run_id = "test_run_raw"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(run_id, run_dir)

    bad_json = '{"segments": [{"id": "s1", "text": "未闭合的字符串...'
    exc = WriterOutputError("Expecting ',' delimiter", raw_text=bad_json)

    with patch("metarpg.agentic.runner.run_writer", side_effect=exc):
        result = run_agentic_turn(
            world=world,
            player_input="测试",
            turn_index=1,
            run_id=run_id,
            history=[],
            run_logger=logger,
        )

    assert result["error"] is not None
    assert result["player_output"] == ""
    assert result["committed"] is False

    # Error turn file must contain raw_writer_output
    error_path = run_dir / "turn_001_error.json"
    assert error_path.exists(), f"Expected error turn file at {error_path}"
    with open(error_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("raw_writer_output") == bad_json, (
        f"raw_writer_output missing or wrong: {data.get('raw_writer_output')!r}"
    )

    # Scorecard should also be written on failure path
    scorecard_path = run_dir / "scorecard_001.json"
    assert scorecard_path.exists(), "Scorecard must be written even on failure"

    logger.close(
        turns_attempted=1,
        turns_completed=0,
        scorecards=[data.get("scorecard", {})],
        hard_failures=["writer_failure"],
        medium_issues=[],
        soft_issues=[],
    )


# ---------------------------------------------------------------------------
# P0: RunLogger artifact completeness
# ---------------------------------------------------------------------------

def test_run_logger_writes_all_artifacts_on_close(tmp_path: Path) -> None:
    """RunLogger must emit events.jsonl, errors.jsonl, run_manifest.json,
    and summary.md when close() is called."""
    run_dir = tmp_path / "run_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger("run_001", run_dir)

    logger.emit(1, "writer", "writer_success", "segments=2")
    logger.log_error(2, "hard_audit", "ValidationError", "something broke")
    logger.close(
        turns_attempted=2,
        turns_completed=1,
        scorecards=[{"player_experience_score": 0.85}],
        hard_failures=["writer_failure"],
        medium_issues=["unregistered_concrete_prop"],
        soft_issues=["too_mechanical"],
    )

    # All four artifact files must exist
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "errors.jsonl").exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "summary.md").exists()

    # Manifest must contain key fields
    with open(run_dir / "run_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["run_id"] == "run_001"
    assert manifest["turns_expected"] == 2
    assert manifest["turns_written"] == 1
    assert manifest["acceptable"] is False  # because hard_failures present
    assert manifest["hard_failures"] == ["writer_failure"]

    # Summary must mention failures and scores
    with open(run_dir / "summary.md", "r", encoding="utf-8") as f:
        summary = f.read()
    assert "writer_failure" in summary
    assert "0.85" in summary


# ---------------------------------------------------------------------------
# P1: Writer repair prompt template
# ---------------------------------------------------------------------------

def test_writer_repair_prompt_contains_error_and_raw() -> None:
    """The repair prompt template must include placeholders for the JSON
    error message and the raw invalid output."""
    from metarpg.agentic.writer_agent import _REPAIR_PROMPT

    assert "{error}" in _REPAIR_PROMPT
    assert "{raw}" in _REPAIR_PROMPT
    assert "Fix JSON syntax only" in _REPAIR_PROMPT
    assert "Do not change story content" in _REPAIR_PROMPT
    assert "temperature=0" not in _REPAIR_PROMPT  # temperature is API param, not prompt text


# ---------------------------------------------------------------------------
# P2: Hard Auditor inventory invention classification
# ---------------------------------------------------------------------------

def test_hard_auditor_unregistered_prop_is_medium_when_inventory_empty() -> None:
    """When inventory_or_handheld is empty and Writer claims prop_usage,
    Hard Auditor must downgrade to medium_issue, not hard_fail."""
    packet = _story_packet()
    packet["player_context"]["inventory_or_handheld"] = []
    segments = [Segment(id="s1", type="player_action", text="你从背包里取出一块干面包吃了起来。")]
    claims = [
        NarrativeClaim(
            segment_id="s1",
            kind="prop_usage",
            subject="player",
            action="eat",
            evidence_span="你从背包里取出一块干面包吃了起来",
            confidence=0.8,
            metadata={"prop": "dry_bread"},
        )
    ]
    scanner = {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }
    patch: list[CandidatePatchEffect] = []
    world = _build_world()

    result = run_hard_audit(packet, segments, claims, scanner, patch, world)

    hard_types = {i["type"] for i in result["issues"]}
    medium_types = {i["type"] for i in result["medium_issues"]}

    assert "state_change_without_support" not in hard_types, (
        f"Empty inventory prop usage should NOT hard-fail, got hard issues: {result['issues']}"
    )
    assert "unregistered_concrete_prop" in medium_types, (
        f"Expected medium unregistered_concrete_prop, got medium_issues: {result['medium_issues']}"
    )


# ---------------------------------------------------------------------------
# P3: Scorecard truthfulness
# ---------------------------------------------------------------------------

def test_scorecard_soft_issues_cap_experience() -> None:
    """Only soft issues must cap player_experience_score at 0.85."""
    sc = TurnScorecard(turn_id="t1")
    sc.soft_issues = ["too_mechanical"]
    sc.soft_issue_count = 1
    assert sc.compute_player_experience() == 0.85


def test_scorecard_medium_issues_cap_experience() -> None:
    """Medium issues must cap player_experience_score at 0.75."""
    sc = TurnScorecard(turn_id="t2")
    sc.medium_issues = ["unregistered_concrete_prop"]
    sc.medium_issue_count = 1
    assert sc.compute_player_experience() == 0.75


def test_scorecard_hard_failures_zero_experience() -> None:
    """Hard failures must force player_experience_score to 0.0."""
    sc = TurnScorecard(turn_id="t3")
    sc.hard_failures = ["hidden_fact_leak"]
    sc.hard_issue_count = 1
    assert sc.compute_player_experience() == 0.0


def test_scorecard_missing_output_zero_experience() -> None:
    """Missing player output must force player_experience_score to 0.0
    regardless of other issues."""
    sc = TurnScorecard(turn_id="t4")
    sc.missing_player_output = True
    sc.soft_issues = ["too_mechanical"]
    assert sc.compute_player_experience() == 0.0


def test_scorecard_clean_turn_full_experience() -> None:
    """A clean turn must score 1.0."""
    sc = TurnScorecard(turn_id="t5")
    assert sc.compute_player_experience() == 1.0


# ---------------------------------------------------------------------------
# P3: Live and eval use same runner contract
# ---------------------------------------------------------------------------

def test_live_and_eval_use_same_runner_contract() -> None:
    """Both interactive play_cli and smoke eval must route through
    run_agentic_turn in runner.py."""
    import metarpg.agentic.play_cli as play_cli_module
    import scripts.agentic_5turn_smoke_test as smoke_module

    # Both modules must import run_agentic_turn from the canonical runner
    assert hasattr(play_cli_module, "run_agentic_turn") or (
        "metarpg.agentic.runner" in str(play_cli_module.__dict__)
    ), "play_cli should use runner.run_agentic_turn"

    assert hasattr(smoke_module, "run_agentic_turn"), (
        "smoke_test must import run_agentic_turn directly"
    )

    # Verify the function signature is the same object
    from metarpg.agentic.runner import run_agentic_turn as canonical_runner

    assert smoke_module.run_agentic_turn is canonical_runner, (
        "smoke_test must use the canonical runner function, not a copy"
    )


# ---------------------------------------------------------------------------
# P3: Runner returns structured dict on success path
# ---------------------------------------------------------------------------

def test_runner_success_dict_keys() -> None:
    """run_agentic_turn must return a dict with the documented keys even
    when mocked so no live LLM is needed."""
    world = build()
    run_id = "test_success"
    run_dir = Path("runtime/agentic_runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(run_id, run_dir)

    fake_writer_output = WriterOutput(
        interpretation="test interpretation",
        segments=[Segment(id="s1", type="sensory", text="一阵风吹过。")],
        candidate_patch=[CandidatePatchEffect(kind="transient_event", args={})],
    )

    with patch("metarpg.agentic.runner.run_writer", return_value=fake_writer_output):
        with patch("metarpg.agentic.runner.run_translator", return_value=[]):
            with patch("metarpg.agentic.runner.scan_segment", return_value={
                "known_entity_hits": [],
                "hidden_fact_alias_hits": [],
                "raw_event_id_hits": [],
                "inner_thought_verb_hits": [],
                "remote_event_cue_hits": [],
                "unsupported_location_mentions": [],
                "claims": [],
            }):
                with patch("metarpg.agentic.runner.run_hard_audit", return_value={
                    "passed": True,
                    "issues": [],
                    "medium_issues": [],
                    "alignment_check": {},
                }):
                    with patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]):
                        with patch("metarpg.agentic.runner.commit_turn"):
                            result = run_agentic_turn(
                                world=world,
                                player_input="看看周围",
                                turn_index=1,
                                run_id=run_id,
                                history=[],
                                run_logger=logger,
                            )

    assert set(result.keys()) >= {
        "draft", "scorecard", "player_output", "committed", "error"
    }
    assert result["error"] is None
    assert result["committed"] is True
    assert result["player_output"] == "一阵风吹过。"
    assert result["scorecard"].grounding_score == 1.0

    logger.close(
        turns_attempted=1,
        turns_completed=1,
        scorecards=[result["scorecard"].to_json()],
        hard_failures=[],
        medium_issues=[],
        soft_issues=[],
    )


if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("v0.6.3 Regression Cases")
    print("=" * 60)

    # Run all tests manually without pytest fixtures
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        test_writer_repair_prompt_contains_error_and_raw()
        print("[PASS] Writer repair prompt template")

        test_hard_auditor_unregistered_prop_is_medium_when_inventory_empty()
        print("[PASS] Hard Auditor unregistered prop is medium")

        test_scorecard_soft_issues_cap_experience()
        test_scorecard_medium_issues_cap_experience()
        test_scorecard_hard_failures_zero_experience()
        test_scorecard_missing_output_zero_experience()
        test_scorecard_clean_turn_full_experience()
        print("[PASS] Scorecard truthfulness (5 cases)")

        test_runner_captures_raw_text_on_writer_failure(tmp / "raw_test")
        print("[PASS] Runner captures raw_text on Writer failure")

        test_run_logger_writes_all_artifacts_on_close(tmp / "logger_test")
        print("[PASS] RunLogger writes all artifacts")

        test_live_and_eval_use_same_runner_contract()
        print("[PASS] Live/eval use same runner contract")

        test_runner_success_dict_keys()
        print("[PASS] Runner success dict keys")

    print("=" * 60)
    print("All v0.6.3 regression cases passed.")
    print("=" * 60)
