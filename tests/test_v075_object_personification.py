"""Targeted repair proof: object personification detection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metarpg.agentic.semantic_judge import judge_object_personification


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_fixture_object_personification_has_agency():
    """The fixture prose personifies black_ash."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_prose_object_personified.json").read_text(encoding="utf-8")
    )
    assert "black_ash" in fixture["visible_objects"]
    assert "站了起来" in fixture["prose"]
    assert "注视" in fixture["prose"]


def test_judge_object_personification_no_client_returns_pass():
    """Without LLM client the judge is permissive (baseline behavior)."""
    fixture = json.loads(
        (FIXTURES_DIR / "bad_prose_object_personified.json").read_text(encoding="utf-8")
    )
    result = judge_object_personification(
        prose=fixture["prose"],
        visible_objects=fixture["visible_objects"],
        client=None,
    )
    # No client = permissive pass
    assert result.verdict == "pass"


def test_judge_object_personification_empty_objects_returns_pass():
    """No visible_objects means nothing to check."""
    result = judge_object_personification(
        prose="那堆黑灰站了起来。",
        visible_objects=[],
        client=None,
    )
    assert result.verdict == "pass"
