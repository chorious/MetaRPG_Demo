"""v0.6.6 regression — Bold-first + Safe fallback pipeline.

Mock-only tests verifying the restored decision-tree pipeline:
  bold > safe_loose > safe_strict > refusal_fallback.

No live LLM required.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.run_logger import RunLogger
from metarpg.agentic.runner import aggregate_v064_stats, run_agentic_turn
from metarpg.agentic.schemas import (
    CandidatePatchEffect,
    FeasibilityReport,
    Segment,
    TurnDraft,
    WriterOutput,
)
from metarpg.agentic.writer_agent import WriterOutputError
from metarpg.scenarios.greyfen import build


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_writer_output(text: str, kind: str = "transient_event",
                      seg_count: int = 1) -> WriterOutput:
    segs = [Segment(id=f"s{i}", type="sensory", text=f"{text}#{i}")
            for i in range(seg_count)] if seg_count else []
    return WriterOutput(
        interpretation=f"mock:{text}",
        segments=segs,
        candidate_patch=[CandidatePatchEffect(kind=kind, args={})],
    )


def _empty_writer_output(label: str) -> WriterOutput:
    return WriterOutput(
        interpretation=f"empty:{label}",
        segments=[],
        candidate_patch=[],
    )


def _accept_feas() -> FeasibilityReport:
    return FeasibilityReport(
        preserve_player_voice=["test"],
        world_response_kind="accept",
    )


def _absence_feas() -> FeasibilityReport:
    return FeasibilityReport(
        preserve_player_voice=["光剑"],
        feasibility_facts=["lightsaber not in world"],
        world_response_kind="absence",
    )


def _empty_scanner_findings() -> dict:
    return {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }


def _pass_audit():
    return {"passed": True, "issues": [], "medium_issues": [], "alignment_check": {}}


def _fail_audit():
    return {
        "passed": False,
        "issues": [{"severity": "hard_fail", "type": "absent_entity_action", "reason": "test"}],
        "medium_issues": [],
        "alignment_check": {},
    }


def _writer_dispatch(by_mode: dict[str, WriterOutput | Exception]):
    """Return a side_effect callable that picks output by run_writer mode kwarg."""
    def _dispatch(*args, **kwargs):
        mode = kwargs.get("mode", "bold")
        # safe_strict_* all map to "safe_strict" bucket for test convenience.
        bucket = "safe_strict" if mode.startswith("safe_strict") else mode
        result = by_mode.get(bucket)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise RuntimeError(f"no mock writer output for mode={mode}")
        return result
    return _dispatch


# ---------------------------------------------------------------------------
# Fast path: Bold passes
# ---------------------------------------------------------------------------

def test_bold_fast_path_when_audit_passes(tmp_path: Path) -> None:
    """When Bold passes audit AND has segments, it wins immediately."""
    world = build()
    (tmp_path / "test_bold").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_bold", tmp_path / "test_bold")

    bold_out = _ok_writer_output("BOLD")

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({"bold": bold_out})),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_accept_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", return_value=_pass_audit()),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="test", turn_index=1,
            run_id="test_bold", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.winner_name == "bold"
    # Only bold should be in writer_candidates (safe writers not spawned)
    assert set(draft.writer_candidates) == {"bold"}
    assert draft.candidate_audits["bold"]["passed"] is True
    assert "BOLD#0" in result["player_output"]
    assert draft.turn_wall_time_s > 0


# ---------------------------------------------------------------------------
# Safe loose fallback
# ---------------------------------------------------------------------------

def test_safe_loose_wins_when_bold_fails(tmp_path: Path) -> None:
    """Bold fails audit -> safe writers spawned; safe_loose passes."""
    world = build()
    (tmp_path / "test_loose").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_loose", tmp_path / "test_loose")

    bold_out = _ok_writer_output("BOLD")
    loose_out = _ok_writer_output("SAFE_LOOSE")
    strict_out = _ok_writer_output("SAFE_STRICT")

    # First hard_audit (bold) fails; then loose passes; strict not reached or also passes.
    audits = [_fail_audit(), _pass_audit(), _pass_audit()]

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({
                  "bold": bold_out,
                  "safe_loose": loose_out,
                  "safe_strict": strict_out,
              })),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_absence_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", side_effect=audits),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="光剑", turn_index=1,
            run_id="test_loose", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.winner_name == "safe_loose"
    assert "bold" in draft.writer_candidates
    assert "safe_loose" in draft.writer_candidates
    assert "SAFE_LOOSE#0" in result["player_output"]


# ---------------------------------------------------------------------------
# Safe strict fallback
# ---------------------------------------------------------------------------

def test_safe_strict_wins_when_bold_and_loose_fail(tmp_path: Path) -> None:
    world = build()
    (tmp_path / "test_strict").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_strict", tmp_path / "test_strict")

    bold_out = _ok_writer_output("BOLD")
    loose_out = _ok_writer_output("SAFE_LOOSE")
    strict_out = _ok_writer_output("SAFE_STRICT")

    # bold FAIL, safe_loose FAIL, safe_strict PASS
    audits = [_fail_audit(), _fail_audit(), _pass_audit()]

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({
                  "bold": bold_out, "safe_loose": loose_out, "safe_strict": strict_out,
              })),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_absence_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", side_effect=audits),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="光剑", turn_index=1,
            run_id="test_strict", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.winner_name == "safe_strict"
    assert "SAFE_STRICT#0" in result["player_output"]


# ---------------------------------------------------------------------------
# Fallback template
# ---------------------------------------------------------------------------

def test_fallback_template_when_all_writers_fail(tmp_path: Path) -> None:
    """All Writer audits fail -> refusal_fallback template wins."""
    world = build()
    (tmp_path / "test_fb").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_fb", tmp_path / "test_fb")

    bold_out = _ok_writer_output("BOLD")
    loose_out = _ok_writer_output("LOOSE")
    strict_out = _ok_writer_output("STRICT")

    # Every audit fails
    audits = [_fail_audit(), _fail_audit(), _fail_audit()]

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({
                  "bold": bold_out, "safe_loose": loose_out, "safe_strict": strict_out,
              })),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_absence_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", side_effect=audits),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="光剑", turn_index=1,
            run_id="test_fb", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.winner_name == "fallback"
    # Fallback prose preserves player voice (e.g. '光剑')
    assert "光剑" in result["player_output"]


# ---------------------------------------------------------------------------
# Empty segments rejected
# ---------------------------------------------------------------------------

def test_empty_segments_candidate_rejected_even_if_audit_passes(tmp_path: Path) -> None:
    """A candidate with zero segments must be rejected, even if audit passes."""
    world = build()
    (tmp_path / "test_empty").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_empty", tmp_path / "test_empty")

    bold_empty = _empty_writer_output("BOLD_EMPTY")
    loose_out = _ok_writer_output("LOOSE_REAL")
    strict_out = _ok_writer_output("STRICT_REAL")

    # bold "passes" audit but has no segments -> must fall through to safe writers
    audits = [_pass_audit(), _pass_audit(), _pass_audit()]

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({
                  "bold": bold_empty, "safe_loose": loose_out, "safe_strict": strict_out,
              })),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_accept_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", side_effect=audits),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="test", turn_index=1,
            run_id="test_empty", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.winner_name == "safe_loose"
    assert "LOOSE_REAL" in result["player_output"]


# ---------------------------------------------------------------------------
# Bold exception preserves v0.6.3 error contract
# ---------------------------------------------------------------------------

def test_bold_exception_returns_error(tmp_path: Path) -> None:
    """Bold raises -> error path, no safe writers spawned, error turn written."""
    world = build()
    (tmp_path / "test_err").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_err", tmp_path / "test_err")

    exc = WriterOutputError("test failure", raw_text="bad{json")

    with (
        patch("metarpg.agentic.runner.run_writer", side_effect=exc),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_accept_feas()),
    ):
        result = run_agentic_turn(
            world=world, player_input="test", turn_index=1,
            run_id="test_err", history=[], run_logger=logger,
        )

    assert result["error"] is not None
    assert result["player_output"] == ""
    assert result["committed"] is False

    err_path = tmp_path / "test_err" / "turn_001_error.json"
    assert err_path.exists()
    import json
    with open(err_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["raw_writer_output"] == "bad{json"


# ---------------------------------------------------------------------------
# Observability surface
# ---------------------------------------------------------------------------

def test_v064_observability_fields_present(tmp_path: Path) -> None:
    """draft must expose feasibility, writer_candidates, candidate_audits,
    winner_name, turn_wall_time_s."""
    world = build()
    (tmp_path / "test_obs").mkdir(parents=True, exist_ok=True)
    logger = RunLogger("test_obs", tmp_path / "test_obs")

    with (
        patch("metarpg.agentic.runner.run_writer",
              side_effect=_writer_dispatch({"bold": _ok_writer_output("BOLD")})),
        patch("metarpg.agentic.runner.run_feasibility", return_value=_accept_feas()),
        patch("metarpg.agentic.runner.run_translator", return_value=[]),
        patch("metarpg.agentic.runner.scan_segment", return_value=_empty_scanner_findings()),
        patch("metarpg.agentic.runner.run_hard_audit", return_value=_pass_audit()),
        patch("metarpg.agentic.runner.run_soft_auditor", return_value=[]),
        patch("metarpg.agentic.runner.commit_turn"),
    ):
        result = run_agentic_turn(
            world=world, player_input="test", turn_index=1,
            run_id="test_obs", history=[], run_logger=logger,
        )

    draft = result["draft"]
    assert draft.feasibility is not None
    assert draft.feasibility.world_response_kind == "accept"
    assert "bold" in draft.writer_candidates
    assert "bold" in draft.candidate_audits
    assert draft.winner_name == "bold"
    assert draft.turn_wall_time_s > 0


# ---------------------------------------------------------------------------
# aggregate_v064_stats
# ---------------------------------------------------------------------------

def test_aggregate_stats_with_safe_distribution() -> None:
    drafts = [
        TurnDraft(draft_id="t1", winner_name="bold", turn_wall_time_s=1.5,
                  candidate_audits={"bold": {"passed": True}}),
        TurnDraft(draft_id="t2", winner_name="safe_loose", turn_wall_time_s=3.0,
                  candidate_audits={"bold": {"passed": False}, "safe_loose": {"passed": True}}),
        TurnDraft(draft_id="t3", winner_name="safe_strict", turn_wall_time_s=4.0,
                  candidate_audits={"bold": {"passed": False}, "safe_loose": {"passed": False},
                                    "safe_strict": {"passed": True}}),
        TurnDraft(draft_id="t4", winner_name="fallback", turn_wall_time_s=2.0,
                  candidate_audits={"bold": {"passed": False}, "safe_loose": {"passed": False},
                                    "safe_strict": {"passed": False}}),
    ]
    stats = aggregate_v064_stats(drafts)
    assert stats["turns"] == 4
    assert stats["bold_pass_rate"] == 0.25  # 1/4 bold pass
    assert stats["safe_loose_pass_rate"] == 0.25
    assert stats["safe_strict_pass_rate"] == 0.25
    assert stats["fallback_count"] == 1
    assert stats["median_turn_wall_time_s"] == 2.5
    wd = stats["winner_distribution"]
    assert wd["bold"] == 1
    assert wd["safe_loose"] == 1
    assert wd["safe_strict"] == 1
    assert wd["fallback"] == 1


def test_aggregate_stats_empty_drafts() -> None:
    assert aggregate_v064_stats([]) == {}


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
