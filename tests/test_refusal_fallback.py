"""Unit tests for refusal_fallback (template-only, no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.refusal_fallback import (
    generate,
    generate_segments,
)
from metarpg.agentic.schemas import FeasibilityReport


def _feas(kind: str, voice: list[str] | None = None) -> FeasibilityReport:
    return FeasibilityReport(
        feasibility_facts=[],
        preserve_player_voice=voice or [],
        world_response_kind=kind,
    )


def test_absence_template_used_when_kind_absence() -> None:
    segs = generate_segments(_feas("absence", ["抽剑"]))
    full = " ".join(s.text for s in segs)
    assert "抽剑" in full
    assert "虚处" in full or "空气" in full


def test_friction_template_used_when_kind_friction() -> None:
    segs = generate_segments(_feas("friction", ["推"]))
    full = " ".join(s.text for s in segs)
    assert "推" in full
    assert "阻力" in full or "慢" in full


def test_reframing_template_used_when_kind_reframing() -> None:
    segs = generate_segments(_feas("reframing", ["读心"]))
    full = " ".join(s.text for s in segs)
    assert "读心" in full
    assert "不太对" in full or "理解" in full


def test_accept_template_used_when_kind_accept_or_unknown() -> None:
    # explicit accept
    segs = generate_segments(_feas("accept", ["看"]))
    full = " ".join(s.text for s in segs)
    assert "看" in full
    # unknown kind also falls back to accept
    segs2 = generate_segments(_feas("totally_unknown_kind", ["看"]))
    full2 = " ".join(s.text for s in segs2)
    assert "看" in full2


def test_preserve_player_voice_appears_in_prose() -> None:
    """The first voice token MUST appear in the fallback prose."""
    for kind in ("absence", "friction", "reframing", "accept"):
        segs = generate_segments(_feas(kind, ["marker_voice"]))
        full = " ".join(s.text for s in segs)
        assert "marker_voice" in full, f"{kind} did not preserve voice"


def test_empty_voice_falls_back_to_placeholder() -> None:
    segs = generate_segments(_feas("absence", []))
    full = " ".join(s.text for s in segs)
    # No KeyError or empty replacement
    assert full.strip()
    assert "{voice}" not in full


def test_generate_returns_writer_output_with_transient_patch() -> None:
    out = generate(_feas("absence", ["斩"]))
    assert out.segments
    assert all(s.transient_only for s in out.segments)
    assert out.candidate_patch
    assert all(e.kind == "transient_event" for e in out.candidate_patch)


def test_no_system_terms_in_player_facing_text() -> None:
    """Prose must not leak schema/audit vocabulary."""
    banned = ["hard_fail", "absent", "absence_kind", "world_response_kind",
              "schema_violation", "feasibility"]
    for kind in ("absence", "friction", "reframing", "accept"):
        segs = generate_segments(_feas(kind, ["test"]))
        full = " ".join(s.text for s in segs).lower()
        for term in banned:
            assert term not in full, f"{kind} leaked '{term}'"


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
