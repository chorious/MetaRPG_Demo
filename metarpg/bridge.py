"""Bridge CLI — v0.5.1.

UPF -> MetaRPG subprocess entry point.
Usage: python -m metarpg.bridge step
Reads JSON request from stdin, writes JSON response to stdout.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

from .bridge_protocol import (
    BridgeDebug,
    BridgeMessage,
    BridgeRequest,
    BridgeResponse,
    BridgeSnapshot,
    BridgeApplyReport,
)
from .bridge_session import load_or_create_session, save_session
from .engine import Engine
from .export_snapshot import export_snapshot
from .narrator import Narrator
from .scenario_hooks import ScenarioHooks
from .scenarios.greyfen import build_hooks


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 for stdin/stdout on Windows
    if sys.platform == "win32":
        try:
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    command = argv[0] if argv else "step"
    if command != "step":
        _write_response(_error_response("unknown_command", f"Unknown command: {command}"))
        return 2

    # Read request JSON from stdin
    try:
        raw = sys.stdin.read()
        if not raw:
            _write_response(_error_response("empty_input", "No JSON input on stdin"))
            return 1
        data = json.loads(raw)
        req = BridgeRequest.from_json(data)
    except json.JSONDecodeError as e:
        _write_response(_error_response("invalid_json", f"Invalid JSON: {e}"))
        return 1
    except Exception as e:
        _write_response(_error_response("parse_error", str(e)))
        return 1

    # Validate protocol version
    pv = data.get("protocol_version", 0)
    if pv != 1:
        _write_response(_error_response("unsupported_protocol", f"Protocol version {pv} not supported"))
        return 1

    # Load or create session
    try:
        world, messages, _ = load_or_create_session(req.session_id)
    except Exception as e:
        _write_response(_error_response("session_load_failed", str(e)))
        return 1

    # Build engine
    hooks = build_hooks()
    force_no_llm = req.options.get("force_no_llm", False)
    narrator = Narrator(enabled=not force_no_llm)
    engine = Engine(world, narrator=narrator, hooks=hooks)

    # Run step
    try:
        rec = engine.step(req.player_text)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        _write_response(_error_response("engine_step_failed", str(e)))
        return 1

    # Build messages
    out_messages: list[BridgeMessage] = []
    if rec.narration:
        out_messages.append(BridgeMessage(speaker="narrator", text=rec.narration))
    if not rec.validation.ok:
        out_messages.append(BridgeMessage(speaker="system", text=f"[Rejected: {rec.validation.reason}]"))

    # Build snapshot
    snap_data = export_snapshot(world)
    snapshot = BridgeSnapshot(
        location=snap_data["player_visible"]["location"],
        nearby_npcs=snap_data["player_visible"]["nearby_npcs"],
        facts=snap_data["player_visible"]["known_facts"],
        known_entities=sorted(world.npcs | world.locations),
        active_hooks=snap_data["debug"]["active_hooks"],
        frontiers=[f["id"] for f in snap_data["debug"]["active_frontiers"]],
        relations=snap_data["upf_panels"]["relations"],
        beliefs=snap_data["upf_panels"]["beliefs"],
    )

    # Build apply report
    applications: list[dict[str, Any]] = []
    for ev in rec.canon_delta.get("events") or []:
        applications.append({"event": {"kind": "event", "args": [str(ev)]}, "outcome": "applied"})
    for ev in rec.canon_delta.get("transient_events") or []:
        applications.append({"event": {"kind": "transient_event", "args": [str(ev)]}, "outcome": "applied"})
    for ev in rec.canon_delta.get("observations") or []:
        applications.append({"event": {"kind": "observe", "args": [str(ev)]}, "outcome": "applied"})
    for f in rec.canon_delta.get("facts_added") or []:
        applications.append({"event": {"kind": "add_fact", "args": [str(f)]}, "outcome": "applied"})
    for f in rec.canon_delta.get("facts_removed") or []:
        applications.append({"event": {"kind": "remove_fact", "args": [str(f)]}, "outcome": "applied"})
    for k in rec.canon_delta.get("knowledge_added") or []:
        applications.append({"event": {"kind": "add_knowledge", "args": [str(k)]}, "outcome": "applied"})
    for rd in rec.canon_delta.get("rel_deltas") or []:
        applications.append({"event": {"kind": "rel_delta", "args": [str(rd)]}, "outcome": "applied"})
    for bd in rec.canon_delta.get("belief_deltas") or []:
        applications.append({"event": {"kind": "belief_delta", "args": [str(bd)]}, "outcome": "applied"})
    for rf in rec.canon_delta.get("risk_flags") or []:
        applications.append({"event": {"kind": "risk_flag", "args": [str(rf)]}, "outcome": "applied"})
    apply_report = BridgeApplyReport(applications=applications)

    # Build debug
    debug = BridgeDebug(
        budget=rec.budget_class,
        touched_frontiers=rec.touched_frontiers,
        top_affordances=rec.affordance_candidates[:5],
        plot_issues=rec.canon_delta.get("risk_flags") or [],
        active_hooks=snap_data["debug"]["active_hooks"],
        claim_summary=rec.claim_summary,
        hypothesis_kind=rec.hypothesis_kind,
        hypothesis_confidence=rec.hypothesis_confidence,
    )

    # Persist session
    messages.extend([{"speaker": m.speaker, "text": m.text} for m in out_messages])
    try:
        save_session(req.session_id, world, messages)
    except Exception as e:
        sys.stderr.write(f"Warning: session save failed: {e}\n")

    resp = BridgeResponse(
        ok=True,
        session_id=req.session_id,
        turn=rec.turn,
        messages=out_messages,
        apply_report=apply_report,
        snapshot=snapshot,
        debug=debug,
    )
    _write_response(resp)
    return 0


def _write_response(resp: BridgeResponse) -> None:
    json_str = json.dumps(resp.to_json(), ensure_ascii=False)
    sys.stdout.write(json_str)
    sys.stdout.flush()


def _error_response(code: str, message: str) -> BridgeResponse:
    from .bridge_protocol import BridgeError
    return BridgeResponse(
        ok=False,
        error=BridgeError(code=code, message=message),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
