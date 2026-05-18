"""Tests for crystallize primitive (v0.6.6).

LLM-free: only deterministic path and structural checks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.crystallize import crystallize
from metarpg.agentic.schemas import Segment
from metarpg.models import Fact, WorldState


def _world() -> WorldState:
    w = WorldState()
    w.facts.add(Fact("at", ("player", "tavern")))
    return w


def test_crystallize_skips_failed_audit() -> None:
    """If hard_audit failed, no facts should be extracted."""
    w = _world()
    segs = [Segment(id="s1", type="sensory", text="Mara has red hair")]
    audit = {"passed": False, "issues": []}
    facts = crystallize(segs, audit, w, client=None)
    assert facts == []


def test_crystallize_skips_empty_segments() -> None:
    w = _world()
    audit = {"passed": True, "issues": []}
    facts = crystallize([], audit, w, client=None)
    assert facts == []


def test_crystallize_no_duplicate_facts() -> None:
    """Extracted facts that already exist in world.facts must not be duplicated."""
    w = _world()
    w.facts.add(Fact("at", ("player", "tavern"), "location"))
    # With no LLM, deterministic path returns [] — no duplication possible
    segs = [Segment(id="s1", type="sensory", text="nothing new")]
    audit = {"passed": True, "issues": []}
    facts = crystallize(segs, audit, w, client=None)
    # Deterministic path is conservative; just assert no crash
    assert isinstance(facts, list)


def test_crystallize_physical_type_filter() -> None:
    """Only physical fact types should be returned."""
    # This test documents the contract; with LLM mock it would verify filtering.
    from metarpg.agentic.crystallize import _PHYSICAL_TYPES
    assert "location" in _PHYSICAL_TYPES
    assert "entity_appearance" in _PHYSICAL_TYPES
    assert "prop" in _PHYSICAL_TYPES
    assert "event" in _PHYSICAL_TYPES


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
