"""Unit tests for refusal_fallback (LLM + template, v0.6.6.1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import metarpg.agentic.refusal_fallback as _rf_mod
from metarpg.agentic.schemas import FeasibilityReport

# Force template fallback by disabling make_client
_rf_mod.make_client = lambda kind="flash": None


def _feas(kind: str, voice: list[str] | None = None) -> FeasibilityReport:
    return FeasibilityReport(
        feasibility_facts=[],
        preserve_player_voice=voice or [],
        world_response_kind=kind,
    )


class _FakeClient:
    def __init__(self, response_text: str) -> None:
        self._text = response_text

    def chat(self, messages, temperature: float = 0.7) -> str:
        return self._text


# ---------------------------------------------------------------------------
# Template fallback (no LLM)
# ---------------------------------------------------------------------------

def test_absence_template_used_when_kind_absence() -> None:
    out = _rf_mod.generate(_feas("absence", ["抽剑"]))
    full = " ".join(s.text for s in out.segments)
    assert "抽剑" in full
    assert "虚处" in full or "空气" in full
    assert any(s.type == "inner_monologue" for s in out.segments)


def test_friction_template_used_when_kind_friction() -> None:
    out = _rf_mod.generate(_feas("friction", ["推"]))
    full = " ".join(s.text for s in out.segments)
    assert "推" in full
    assert "阻力" in full or "慢" in full


def test_reframing_template_used_when_kind_reframing() -> None:
    out = _rf_mod.generate(_feas("reframing", ["读心"]))
    full = " ".join(s.text for s in out.segments)
    assert "读心" in full
    assert "不太对" in full or "理解" in full


def test_accept_template_used_when_kind_accept_or_unknown() -> None:
    out = _rf_mod.generate(_feas("accept", ["看"]))
    full = " ".join(s.text for s in out.segments)
    assert "看" in full
    out2 = _rf_mod.generate(_feas("totally_unknown_kind", ["看"]))
    full2 = " ".join(s.text for s in out2.segments)
    assert "看" in full2


def test_preserve_player_voice_appears_in_prose() -> None:
    for kind in ("absence", "friction", "reframing", "accept"):
        out = _rf_mod.generate(_feas(kind, ["marker_voice"]))
        full = " ".join(s.text for s in out.segments)
        assert "marker_voice" in full, f"{kind} did not preserve voice"


def test_empty_voice_falls_back_to_placeholder() -> None:
    out = _rf_mod.generate(_feas("absence", []))
    full = " ".join(s.text for s in out.segments)
    assert full.strip()
    assert "{voice}" not in full


def test_generate_returns_writer_output_with_transient_patch() -> None:
    out = _rf_mod.generate(_feas("absence", ["斩"]))
    assert out.segments
    assert all(s.transient_only for s in out.segments)
    assert out.candidate_patch
    assert all(e.kind == "transient_event" for e in out.candidate_patch)


def test_no_system_terms_in_player_facing_text() -> None:
    banned = [
        "hard_fail", "absent", "absence_kind", "world_response_kind",
        "schema_violation", "feasibility",
    ]
    for kind in ("absence", "friction", "reframing", "accept"):
        out = _rf_mod.generate(_feas(kind, ["test"]))
        full = " ".join(s.text for s in out.segments).lower()
        for term in banned:
            assert term not in full, f"{kind} leaked '{term}'"


# ---------------------------------------------------------------------------
# LLM path (mock client)
# ---------------------------------------------------------------------------

def test_llm_path_returns_inner_monologue_segments() -> None:
    raw = json.dumps({
        "segments": [
            {"id": "rf1", "type": "inner_monologue", "text": "(你的手指还停在吧台边缘。)"},
            {"id": "rf2", "type": "sensory", "text": "铜币的凉意还在掌心。"},
        ],
        "candidate_patch": [
            {"kind": "transient_event", "args": {"name": "refusal", "description": "..."}}
        ],
    }, ensure_ascii=False)
    out = _rf_mod.generate(_feas("absence", ["铜币"]), client=_FakeClient(raw))
    assert len(out.segments) == 2
    assert out.segments[0].type == "inner_monologue"
    assert "手指" in out.segments[0].text


def test_llm_empty_segments_falls_back_to_template() -> None:
    """LLM returns empty segments -> must fall back to template, not crash."""
    raw = json.dumps({"segments": [], "candidate_patch": []}, ensure_ascii=False)
    out = _rf_mod.generate(_feas("friction", ["推"]), client=_FakeClient(raw))
    assert out.segments  # template fallback should provide segments
    assert any(s.type == "inner_monologue" for s in out.segments)


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
