"""v0.5.1 bridge tests — UPF playable bridge.

Per planVer0.5.1 §12. Verifies:
- Bridge protocol serialization round-trip
- Bridge CLI returns valid JSON for valid input
- Invalid JSON returns error response, not crash
- Session save/load preserves world state
- End-to-end Greyfen scenario through bridge
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from metarpg.bridge_protocol import (
    BridgeDebug,
    BridgeMessage,
    BridgeRequest,
    BridgeResponse,
    BridgeSnapshot,
    BridgeApplyReport,
    BridgeError,
)
from metarpg.bridge_session import (
    load_or_create_session,
    save_session,
    _session_path,
    DEFAULT_SESSION_DIR,
)
from metarpg.export_snapshot import export_snapshot
from metarpg.models import Fact, WorldState
from metarpg.scenarios.greyfen import build


# ---------- Protocol serialization ----------


def test_request_round_trip():
    req = BridgeRequest(
        command="step",
        session_id="test_01",
        player_text="推门进入酒馆",
        language="zh-CN",
        options={"include_debug": True},
    )
    data = req.to_json()
    req2 = BridgeRequest.from_json(data)
    assert req2.command == "step"
    assert req2.session_id == "test_01"
    assert req2.player_text == "推门进入酒馆"


def test_response_round_trip():
    resp = BridgeResponse(
        ok=True,
        session_id="test_01",
        turn=3,
        messages=[BridgeMessage(speaker="narrator", text="你推开了门。")],
        snapshot=BridgeSnapshot(location="tavern", nearby_npcs=["mara"]),
        debug=BridgeDebug(budget="large", touched_frontiers=["scene_boundary:tavern"]),
    )
    data = resp.to_json()
    resp2 = BridgeResponse.from_json(data)
    assert resp2.ok
    assert resp2.messages[0].speaker == "narrator"
    assert resp2.snapshot.location == "tavern"
    assert resp2.debug.budget == "large"


# ---------- Bridge CLI ----------


def _call_bridge(payload: dict) -> dict:
    proc = subprocess.run(
        ["python", "-m", "metarpg.bridge", "step"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        cwd=r"E:\GameDesign\MetaRPG_Dev",
        encoding="utf-8",
    )
    assert proc.returncode in (0, 1), f"Unexpected exit code {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout)


def test_bridge_cli_valid_request():
    """§12.1: Bridge CLI returns valid JSON with ok=true."""
    payload = {
        "protocol_version": 1,
        "command": "step",
        "session_id": "test_cli_valid",
        "player_text": "环顾四周",
        "language": "zh-CN",
        "options": {"force_no_llm": True},
    }
    resp = _call_bridge(payload)
    assert resp.get("ok") is True, f"Expected ok=true, got {resp}"
    assert "messages" in resp
    assert "snapshot" in resp
    assert "debug" in resp


def test_bridge_cli_invalid_json():
    """§12.2: Invalid JSON returns ok=false with error code."""
    proc = subprocess.run(
        ["python", "-m", "metarpg.bridge", "step"],
        input="not json at all",
        capture_output=True,
        text=True,
        cwd=r"E:\GameDesign\MetaRPG_Dev",
        encoding="utf-8",
    )
    assert proc.returncode == 1
    resp = json.loads(proc.stdout)
    assert resp.get("ok") is False
    assert "error" in resp


def test_bridge_cli_unsupported_protocol():
    """Unsupported protocol version returns error."""
    payload = {
        "protocol_version": 99,
        "command": "step",
        "session_id": "test_proto",
        "player_text": "test",
    }
    resp = _call_bridge(payload)
    assert resp.get("ok") is False
    assert resp.get("error", {}).get("code") == "unsupported_protocol"


# ---------- Session save/load ----------


def test_session_save_and_load():
    """§12.5: Save/load preserves world state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sid = "test_save_load"
        world, messages, turn = load_or_create_session(sid, base_dir=tmpdir)
        # Mutate world
        world.turn = 5
        world.facts.add(Fact("test", ("a", "b")))
        save_session(sid, world, messages, base_dir=tmpdir)

        world2, messages2, turn2 = load_or_create_session(sid, base_dir=tmpdir)
        assert world2.turn == 5
        assert Fact("test", ("a", "b")) in world2.facts


def test_session_new_when_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        sid = "brand_new"
        world, messages, turn = load_or_create_session(sid, base_dir=tmpdir)
        assert turn == 0
        assert world.turn == 0


# ---------- Snapshot export ----------


def test_export_snapshot_structure():
    w = build()
    snap = export_snapshot(w)
    assert "player_visible" in snap
    assert "upf_panels" in snap
    assert "debug" in snap
    assert snap["player_visible"]["location"] == "tavern"
    assert "mara" in snap["player_visible"]["nearby_npcs"]


def test_export_snapshot_debug_has_frontiers():
    w = build()
    snap = export_snapshot(w)
    debug = snap["debug"]
    assert "turn" in debug
    assert "active_hooks" in debug


# ---------- End-to-end scenario ----------


# ---------- Chinese bridge regression tests ----------


def test_bridge_chinese_go_to_guard_post():
    """去守卫站 -> snapshot.location=guard_post."""
    session_id = "test_zh_go_guard"
    path = _session_path(session_id, base_dir=DEFAULT_SESSION_DIR)
    if os.path.exists(path):
        os.remove(path)

    # First look around to establish state
    _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "环顾四周",
        "options": {"force_no_llm": True},
    })

    resp = _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "去守卫站",
        "options": {"force_no_llm": True},
    })
    assert resp["ok"] is True, f"go_to_guard_post failed: {resp.get('error')}"
    assert resp["snapshot"]["location"] == "guard_post", (
        f"Expected location=guard_post, got {resp['snapshot']['location']}"
    )
    assert "rusk" in resp["snapshot"]["nearby_npcs"], (
        f"Expected Rusk nearby at guard_post, got {resp['snapshot']['nearby_npcs']}"
    )


def test_bridge_chinese_ask_mara_about_mine():
    """问玛拉关于矿场 -> accepted local social action."""
    session_id = "test_zh_ask_mara"
    path = _session_path(session_id, base_dir=DEFAULT_SESSION_DIR)
    if os.path.exists(path):
        os.remove(path)

    resp = _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "问玛拉关于矿场",
        "options": {"force_no_llm": True},
    })
    assert resp["ok"] is True, f"ask_mara failed: {resp.get('error')}"
    # Should be accepted (not rejected by validation)
    assert not any(
        m["speaker"] == "system" and "Rejected" in m["text"]
        for m in resp["messages"]
    ), f"ask_mara was rejected: {resp['messages']}"
    assert resp["messages"][0]["speaker"] == "narrator"


def test_bridge_chinese_tell_mara_about_recent_events():
    """将刚才的情形告诉玛拉 -> hook resolves after prior setup."""
    session_id = "test_zh_tell_mara"
    path = _session_path(session_id, base_dir=DEFAULT_SESSION_DIR)
    if os.path.exists(path):
        os.remove(path)

    # Step 1: look around at tavern
    _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "环顾四周",
        "options": {"force_no_llm": True},
    })

    # Step 2: go to guard post to generate an event worth reporting
    _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "去守卫站",
        "options": {"force_no_llm": True},
    })

    # Step 3: observe at guard post to create more state
    _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "观察拉斯克",
        "options": {"force_no_llm": True},
    })

    # Step 4: return to tavern
    _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "去酒馆",
        "options": {"force_no_llm": True},
    })

    # Step 5: tell Mara about recent events
    resp = _call_bridge({
        "protocol_version": 1,
        "command": "step",
        "session_id": session_id,
        "player_text": "将刚才的情形告诉玛拉",
        "options": {"force_no_llm": True},
    })
    assert resp["ok"] is True, f"tell_mara failed: {resp.get('error')}"
    # Should be accepted and narrated
    assert resp["messages"][0]["speaker"] == "narrator"
    # Should not be a validation rejection
    assert not any(
        m["speaker"] == "system" and "Rejected" in m["text"]
        for m in resp["messages"]
    ), f"tell_mara was rejected: {resp['messages']}"


def test_bridge_greyfen_walkthrough():
    """Run a short Greyfen walkthrough through the bridge."""
    session_id = "test_greyfen_walk"
    # Clean up any prior session
    path = _session_path(session_id, base_dir=DEFAULT_SESSION_DIR)
    if os.path.exists(path):
        os.remove(path)

    steps = [
        ("环顾四周", "narrator"),
        ("问玛拉最近的消息", "narrator"),
        ("去守卫站", "narrator"),
    ]
    for text, expected_speaker in steps:
        payload = {
            "protocol_version": 1,
            "command": "step",
            "session_id": session_id,
            "player_text": text,
            "options": {"force_no_llm": True},
        }
        resp = _call_bridge(payload)
        assert resp["ok"] is True, f"Step '{text}' failed: {resp.get('error')}"
        assert len(resp["messages"]) > 0
        assert resp["messages"][0]["speaker"] == expected_speaker

    # Load session back and verify turn advanced
    world, _, _ = load_or_create_session(session_id)
    assert world.turn >= 3
