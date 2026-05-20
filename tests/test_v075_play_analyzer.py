"""Targeted repair proof: play analyzer detects continuity breaks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_play_run import analyze_run, _check_state_continuity, _extract_public_facts


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_fixture_continuity_break_has_drink_contradiction():
    """The continuity fixture has a drank-then-untouched contradiction."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_play_state_continuity_break.json").read_text(encoding="utf-8")
    )
    turns = fixture["turns"]
    assert len(turns) == 2
    assert "麦酒" in turns[0]["player_output"]
    assert "还没碰" in turns[1]["player_output"]


def test_check_state_continuity_detects_drank_then_untouched():
    """_check_state_continuity flags the contradiction."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_play_state_continuity_break.json").read_text(encoding="utf-8")
    )
    prev_turn = fixture["turns"][0]
    curr_turn = fixture["turns"][1]
    issues = _check_state_continuity(prev_turn, curr_turn)
    assert len(issues) >= 1
    assert any(i["type"] == "drank_then_untouched" for i in issues)


def test_analyze_run_detects_continuity_break(tmp_path: Path) -> None:
    """Full play analyzer run on a synthetic run directory flags the break."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_play_state_continuity_break.json").read_text(encoding="utf-8")
    )
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()

    # Write synthetic turn files
    for i, turn in enumerate(fixture["turns"]):
        turn_file = run_dir / f"turn_{i+1:03d}.json"
        turn_file.write_text(json.dumps(turn, ensure_ascii=False), encoding="utf-8")
        # Write matching scorecard
        scorecard = {
            "turn_id": turn["turn_id"],
            "player_experience_score": 0.85,
            "notes": [],
        }
        (run_dir / f"scorecard_{i+1:03d}.json").write_text(
            json.dumps(scorecard, ensure_ascii=False), encoding="utf-8"
        )

    result = analyze_run(run_dir)
    assert result["state_continuity_issue_count"] >= 1
