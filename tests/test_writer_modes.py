"""Unit tests for writer_agent (bold + safe modes, v0.6.6 restored)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.schemas import FeasibilityReport
from metarpg.agentic.writer_agent import (
    _SAFE_LOOSE_PROMPT,
    _SAFE_PROMPT_ABSENCE,
    _SAFE_PROMPT_FRICTION,
    _SAFE_PROMPT_REFRAMING,
    _SAFE_PROMPT_ACCEPT,
    _SYSTEM_PROMPT,
    _build_feasibility_block,
    _build_prompt,
    _select_system_prompt,
    run_writer,
    safe_mode_for_kind,
)


def _packet() -> dict:
    return {
        "scene": {
            "location": "tavern",
            "visible_entities": ["player", "mara"],
            "visible_objects": [],
            "atmosphere": "calm",
        },
        "player_context": {
            "known_facts": [],
            "recent_events": [],
            "inventory_or_handheld": [],
        },
        "npc_surface": {},
        "allowed_effect_kinds": ["transient_event"],
        "allowed_reveals": [],
        "forbidden": {},
    }


def test_bold_mode_returns_original_system_prompt() -> None:
    prompt, kind = _select_system_prompt("bold")
    assert prompt is _SYSTEM_PROMPT
    assert kind == "flash"


def test_feasibility_block_empty_when_none() -> None:
    assert _build_feasibility_block(None) == ""


def test_feasibility_block_empty_when_no_facts_or_voice() -> None:
    feas = FeasibilityReport()
    assert _build_feasibility_block(feas) == ""


def test_feasibility_block_renders_facts_and_voice() -> None:
    feas = FeasibilityReport(
        feasibility_facts=["world has no lightsaber", "Rusk is absent"],
        preserve_player_voice=["抽出", "斩"],
    )
    block = _build_feasibility_block(feas)
    assert "FEASIBILITY CONTEXT" in block
    assert "world has no lightsaber" in block
    assert "Rusk is absent" in block
    assert "抽出" in block
    assert "斩" in block
    assert block.endswith("\n\n")


def test_build_prompt_injects_facts_when_feasibility_present() -> None:
    feas = FeasibilityReport(
        feasibility_facts=["test_fact_marker"],
        preserve_player_voice=["test_voice_marker"],
    )
    prompt = _build_prompt(_packet(), "test_input", feasibility=feas)
    assert "test_fact_marker" in prompt
    assert "test_voice_marker" in prompt
    assert "FEASIBILITY CONTEXT" in prompt
    assert "STORY PACKET" in prompt


def test_build_prompt_no_injection_when_feasibility_none() -> None:
    prompt = _build_prompt(_packet(), "test_input", feasibility=None)
    assert "FEASIBILITY CONTEXT" not in prompt
    assert prompt.startswith("STORY PACKET")


# ---------------------------------------------------------------------------
# Integration with run_writer via fake client (verify prompt actually used)
# ---------------------------------------------------------------------------

class _CapturingClient:
    """Captures the messages it was called with, returns canned JSON."""
    def __init__(self) -> None:
        self.last_messages: list[dict] | None = None
        self.last_temperature: float | None = None

    def chat(self, messages, temperature: float = 0.7) -> str:
        self.last_messages = messages
        self.last_temperature = temperature
        return json.dumps({
            "interpretation": "ok",
            "segments": [],
            "candidate_patch": [],
            "assumptions": [],
            "risk_notes": [],
        })


def test_run_writer_bold_uses_bold_prompt() -> None:
    client = _CapturingClient()
    run_writer(_packet(), "看看", client=client, temperature=0.8)
    assert client.last_messages is not None
    sys_msg = client.last_messages[0]["content"]
    assert sys_msg is _SYSTEM_PROMPT
    user_msg = client.last_messages[1]["content"]
    assert "FEASIBILITY CONTEXT" not in user_msg
    assert client.last_temperature == 0.8


def test_run_writer_injects_facts() -> None:
    client = _CapturingClient()
    feas = FeasibilityReport(
        feasibility_facts=["marker_fact"],
        preserve_player_voice=["marker_voice"],
    )
    run_writer(
        _packet(), "测试", client=client,
        feasibility=feas, temperature=0.3,
    )
    sys_msg = client.last_messages[0]["content"]
    assert sys_msg is _SYSTEM_PROMPT
    user_msg = client.last_messages[1]["content"]
    assert "marker_fact" in user_msg
    assert "marker_voice" in user_msg
    assert client.last_temperature == 0.3


# ---------------------------------------------------------------------------
# Safe modes (v0.6.6 restored after v0.6.6-radical-simplify regression)
# ---------------------------------------------------------------------------

def test_safe_loose_mode_uses_safe_loose_prompt() -> None:
    prompt, kind = _select_system_prompt("safe_loose")
    assert prompt is _SAFE_LOOSE_PROMPT
    assert kind == "local"


def test_safe_strict_modes_route_per_kind() -> None:
    expected = {
        "safe_strict_absence":   _SAFE_PROMPT_ABSENCE,
        "safe_strict_friction":  _SAFE_PROMPT_FRICTION,
        "safe_strict_reframing": _SAFE_PROMPT_REFRAMING,
        "safe_strict_accept":    _SAFE_PROMPT_ACCEPT,
    }
    for mode, prompt_obj in expected.items():
        prompt, kind = _select_system_prompt(mode)
        assert prompt is prompt_obj, f"{mode} did not route to its prompt"
        assert kind == "local"


def test_unknown_mode_raises() -> None:
    import pytest as _pt
    with _pt.raises(ValueError):
        _select_system_prompt("not_a_real_mode")


def test_safe_mode_for_kind_maps_correctly() -> None:
    assert safe_mode_for_kind("absence") == "safe_strict_absence"
    assert safe_mode_for_kind("friction") == "safe_strict_friction"
    assert safe_mode_for_kind("reframing") == "safe_strict_reframing"
    assert safe_mode_for_kind("accept") == "safe_strict_accept"
    assert safe_mode_for_kind("garbage") == "safe_strict_accept"


def test_run_writer_safe_loose_uses_safe_prompt() -> None:
    """Safe loose mode must inject feasibility facts AND use the loose prompt."""
    client = _CapturingClient()
    feas = FeasibilityReport(
        feasibility_facts=["loose_marker_fact"],
        preserve_player_voice=["loose_voice"],
    )
    run_writer(_packet(), "测试", client=client, mode="safe_loose",
               feasibility=feas, temperature=0.3)
    sys_msg = client.last_messages[0]["content"]
    assert sys_msg is _SAFE_LOOSE_PROMPT
    user_msg = client.last_messages[1]["content"]
    assert "loose_marker_fact" in user_msg
    assert "loose_voice" in user_msg


def test_run_writer_safe_strict_absence_uses_absence_prompt() -> None:
    """safe_strict_absence injects facts AND uses absence prompt."""
    client = _CapturingClient()
    feas = FeasibilityReport(
        feasibility_facts=["abs_marker_fact"],
        preserve_player_voice=["抽出"],
        world_response_kind="absence",
    )
    run_writer(_packet(), "光剑", client=client,
               mode="safe_strict_absence", feasibility=feas, temperature=0.3)
    sys_msg = client.last_messages[0]["content"]
    assert sys_msg is _SAFE_PROMPT_ABSENCE
    user_msg = client.last_messages[1]["content"]
    assert "abs_marker_fact" in user_msg
    assert "抽出" in user_msg


if __name__ == "__main__":
    import pytest as _pt
    sys.exit(_pt.main([__file__, "-v"]))
