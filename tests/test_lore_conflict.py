"""Tests for lore_conflict primitive (v0.6.6).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.lore_conflict import (
    detect_conflict,
    get_conflict_surface,
    record_conflict,
)
from metarpg.models import Fact, WorldState


def _world() -> WorldState:
    w = WorldState()
    w.facts.add(Fact("well_dug_by", ("well", "mara_grandfather")))
    return w


def test_detect_conflict_same_predicate_different_value() -> None:
    w = _world()
    new = Fact("well_dug_by", ("well", "community"))
    conflicts = detect_conflict(new, w)
    assert len(conflicts) == 1
    old, new_found = conflicts[0]
    assert str(old) == "well_dug_by(well,mara_grandfather)"
    assert str(new_found) == "well_dug_by(well,community)"


def test_detect_conflict_no_match() -> None:
    w = _world()
    new = Fact("well_dug_by", ("well", "mara_grandfather"))  # same as existing
    conflicts = detect_conflict(new, w)
    assert conflicts == []


def test_detect_conflict_different_predicate() -> None:
    w = _world()
    new = Fact("color", ("well", "grey"))
    conflicts = detect_conflict(new, w)
    assert conflicts == []


def test_record_conflict_stores_pair() -> None:
    w = _world()
    pair = (Fact("a", ("x", "y")), Fact("a", ("x", "z")))
    record_conflict(w, pair)
    assert hasattr(w, "lore_conflicts")
    assert len(w.lore_conflicts) == 1  # type: ignore[attr-defined]


def test_record_conflict_dedups() -> None:
    w = _world()
    pair = (Fact("a", ("x", "y")), Fact("a", ("x", "z")))
    record_conflict(w, pair)
    record_conflict(w, pair)  # duplicate
    assert len(w.lore_conflicts) == 1  # type: ignore[attr-defined]


def test_get_conflict_surface_format() -> None:
    w = _world()
    record_conflict(w, (Fact("a", ("x", "y")), Fact("a", ("x", "z"))))
    surface = get_conflict_surface(w)
    assert len(surface) == 1
    assert "fact_a" in surface[0]
    assert "fact_b" in surface[0]


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
