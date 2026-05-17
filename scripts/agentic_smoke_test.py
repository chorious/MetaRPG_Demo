"""Agentic v0.6 smoke test — real LLM pipeline.

Runs one turn end-to-end:
1. Build story packet from Greyfen world
2. Writer (DeepSeek Flash) -> segments + candidate_patch
3. Translator (Qwen3.6) -> narrative claims
4. Scanner -> deterministic findings
5. Hard Auditor -> audit report
6. Score -> acceptability
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, r"E:\GameDesign\MetaRPG_Dev")

from metarpg.agentic.story_packet import build_story_packet
from metarpg.agentic.writer_agent import run_writer
from metarpg.agentic.translator_agent import run_translator
from metarpg.agentic.scanner import scan_segment
from metarpg.agentic.hard_auditor import run_hard_audit
from metarpg.agentic.scorecard import TurnScorecard
from metarpg.scenarios.greyfen import build


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    world = build()
    player_input = "一饮而尽"

    print("=" * 60)
    print(f"Agentic Smoke Test: {player_input}")
    print("=" * 60)

    # 1. Story packet
    print("\n[1] Building story packet...")
    story_packet = build_story_packet(world)
    print(json.dumps(story_packet, ensure_ascii=False, indent=2)[:800] + "\n...")

    # 2. Writer
    print("\n[2] Calling Writer (DeepSeek Flash)...")
    try:
        writer_output = run_writer(story_packet, player_input)
        print(f"Interpretation: {writer_output.interpretation}")
        print(f"Segments: {len(writer_output.segments)}")
        for s in writer_output.segments:
            print(f"  [{s.id}] {s.type}: {s.text[:60]}...")
            print(f"       patch_refs={s.patch_refs}, transient_only={s.transient_only}")
        print(f"Candidate patch: {len(writer_output.candidate_patch)} effects")
        for e in writer_output.candidate_patch:
            print(f"  {e.kind}: {e.args}")
        if writer_output.risk_notes:
            print(f"Risk notes: {writer_output.risk_notes}")
    except Exception as e:
        print(f"Writer failed: {e}")
        return 1

    # 3. Translator
    print("\n[3] Calling Translator (Qwen3.6)...")
    try:
        claims = run_translator(writer_output.segments, story_packet)
        print(f"Claims: {len(claims)}")
        for c in claims:
            print(f"  [{c.segment_id}] {c.kind}: {c.evidence_span[:40]}... (conf={c.confidence})")
    except Exception as e:
        print(f"Translator failed: {e}")
        claims = []

    # 4. Scanner
    print("\n[4] Running deterministic scanner...")
    scanner_findings: dict[str, list] = {
        "known_entity_hits": [],
        "hidden_fact_alias_hits": [],
        "raw_event_id_hits": [],
        "inner_thought_verb_hits": [],
        "remote_event_cue_hits": [],
        "unsupported_location_mentions": [],
        "claims": [],
    }
    known_entities = story_packet.get("scene", {}).get("visible_entities", [])
    known_locations = list(world.locations)
    hidden_aliases = story_packet.get("forbidden", {}).get("hidden_fact_aliases", [])
    for s in writer_output.segments:
        findings = scan_segment(s.id, s.text, known_entities, known_locations, hidden_aliases)
        for k, v in findings.items():
            if isinstance(v, list):
                scanner_findings.setdefault(k, []).extend(v)
    print(f"Scanner hits: { {k: len(v) for k, v in scanner_findings.items() if v} }")

    # 5. Hard Auditor
    print("\n[5] Running Hard Auditor...")
    audit = run_hard_audit(
        story_packet,
        writer_output.segments,
        claims,
        scanner_findings,
        writer_output.candidate_patch,
        world,
    )
    print(f"Passed: {audit['passed']}")
    if audit["issues"]:
        for issue in audit["issues"]:
            print(f"  [{issue['severity']}] {issue['type']}: {issue['reason']}")
    else:
        print("  No hard issues found.")

    # 6. Scorecard
    print("\n[6] Scorecard...")
    sc = TurnScorecard()
    sc.hidden_leak_count = sum(1 for c in claims if c.kind == "hidden_fact_reference")
    sc.absent_entity_action_count = sum(1 for c in claims if c.kind == "remote_event")
    sc.raw_debug_exposure_count = len(scanner_findings.get("raw_event_id_hits", []))
    sc.patch_alignment_score = 1.0 if audit["alignment_check"]["claims_without_patch_support"] == 0 else 0.5
    sc.action_understanding_score = 1.0 if writer_output.interpretation else 0.0
    sc.grounding_score = 1.0 if audit["passed"] else 0.0
    sc.player_experience_score = 1.0 if audit["passed"] else 0.0
    print(f"  Grounding: {sc.grounding_score}")
    print(f"  Patch alignment: {sc.patch_alignment_score}")
    print(f"  Action understanding: {sc.action_understanding_score}")
    print(f"  Acceptable: {sc.is_acceptable()}")

    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)
    return 0 if sc.is_acceptable() else 1


if __name__ == "__main__":
    sys.exit(main())
