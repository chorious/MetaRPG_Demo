"""Tests for analyzer metrics taxonomy unification (v0.7.4 Phase 1)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.analyze_agentic_run import _analyze_turn, _compute_summary


def _make_artifact_dir(tmp: Path, turn_idx: int, artifacts: dict[str, dict]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for kind, data in artifacts.items():
        p = tmp / f"artifact_{turn_idx:03d}_{kind}.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        paths[kind] = p
    return paths


class TestFallbackTaxonomy:
    """Verify fallback is split into director_schema vs validation_rejection."""

    def test_director_schema_fallback_classified(self, tmp_path: Path):
        artifacts = _make_artifact_dir(
            tmp_path,
            1,
            {
                "resolved_intent": {"action_type": "move", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {
                    "note": "fallback (Director schema parse failed)",
                    "parsed": {"operations": [], "commitments": []},
                },
                "transaction_validated": {"status": "accepted", "downgrades": []},
                "post_render": {"status": "pass", "issues": [], "semantic_judgments": []},
                "motif_schedule": {"debug": {}},
            },
        )
        turn = _analyze_turn(1, artifacts)
        assert turn["source"] == "fallback"
        assert turn["fallback_type"] == "director_schema_fallback"
        assert not turn["rejected"]

    def test_validation_rejection_fallback_classified(self, tmp_path: Path):
        artifacts = _make_artifact_dir(
            tmp_path,
            1,
            {
                "resolved_intent": {"action_type": "inspect", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {
                    "director_raw_output": {"operations": [{"kind": "inspect", "params": {}}]},
                    "parsed": {"operations": [{"kind": "inspect", "params": {}}], "commitments": []},
                },
                "transaction_validated": {"status": "rejected", "downgrades": []},
                "post_render": {"status": "pass", "issues": [], "semantic_judgments": []},
                "motif_schedule": {"debug": {}},
            },
        )
        turn = _analyze_turn(1, artifacts)
        # raw still looks like director output, but validator rejected it
        assert turn["source"] == "director"
        assert turn["fallback_type"] == "validation_rejection_fallback"
        assert turn["rejected"]

    def test_total_fallback_equals_component_sum(self, tmp_path: Path):
        turns_data = [
            {
                "resolved_intent": {"action_type": "move", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {
                    "note": "fallback",
                    "parsed": {"operations": [], "commitments": []},
                },
                "transaction_validated": {"status": "accepted", "downgrades": []},
                "post_render": {"status": "pass", "issues": [], "semantic_judgments": []},
                "motif_schedule": {"debug": {}},
            },
            {
                "resolved_intent": {"action_type": "inspect", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {
                    "director_raw_output": {"ops": []},
                    "parsed": {"operations": [], "commitments": []},
                },
                "transaction_validated": {"status": "rejected", "downgrades": []},
                "post_render": {"status": "pass", "issues": [], "semantic_judgments": []},
                "motif_schedule": {"debug": {}},
            },
            {
                "resolved_intent": {"action_type": "move", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {
                    "note": "deterministic_movement",
                    "parsed": {"operations": [], "commitments": []},
                },
                "transaction_validated": {"status": "accepted", "downgrades": []},
                "post_render": {"status": "pass", "issues": [], "semantic_judgments": []},
                "motif_schedule": {"debug": {}},
            },
        ]
        turns = []
        for idx, data in enumerate(turns_data, start=1):
            arts = _make_artifact_dir(tmp_path, idx, data)
            turns.append(_analyze_turn(idx, arts))

        summary = _compute_summary(turns)
        ft = summary["fallback_taxonomy"]
        assert ft["director_schema_fallback_count"] == 1
        assert ft["validation_rejection_fallback_count"] == 1
        assert ft["total_fallback_count"] == 2
        assert summary["validator"]["rejected_then_fallback_count"] == 1


class TestPostRenderInitialVsFinal:
    def test_initial_failed_counts_unrepaired(self, tmp_path: Path):
        artifacts = _make_artifact_dir(
            tmp_path,
            1,
            {
                "resolved_intent": {"action_type": "inspect", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {"note": "director", "parsed": {"operations": [], "commitments": []}},
                "transaction_validated": {"status": "accepted", "downgrades": []},
                "post_render": {
                    "status": "failed",
                    "issues": ["L2 semantic: hidden truth exposure"],
                    "semantic_judgments": [],
                    "repair_attempted": False,
                },
                "motif_schedule": {"debug": {}},
            },
        )
        turn = _analyze_turn(1, artifacts)
        summary = _compute_summary([turn])
        assert summary["post_render"]["initial_failed"] == 1
        assert summary["post_render"]["final_failed"] == 1
        assert summary["post_render"]["final_pass"] == 0

    def test_repaired_counts_as_final_pass(self, tmp_path: Path):
        artifacts = _make_artifact_dir(
            tmp_path,
            1,
            {
                "resolved_intent": {"action_type": "inspect", "targets": [], "unresolved": []},
                "narrative_frame": {"active_hooks": [], "candidate_hints": [], "motifs_to_use": []},
                "transaction_raw": {"note": "director", "parsed": {"operations": [], "commitments": []}},
                "transaction_validated": {"status": "accepted", "downgrades": []},
                "post_render": {
                    "status": "repaired",
                    "issues": [],
                    "semantic_judgments": [],
                    "repair_attempted": True,
                },
                "motif_schedule": {"debug": {}},
            },
        )
        turn = _analyze_turn(1, artifacts)
        summary = _compute_summary([turn])
        assert summary["post_render"]["initial_pass"] == 0  # was failed before repair
        assert summary["post_render"]["repaired"] == 1
        assert summary["post_render"]["final_pass"] == 1
        assert summary["post_render"]["final_failed"] == 0
