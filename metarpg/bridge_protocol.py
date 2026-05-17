"""Bridge protocol — v0.5.1.

JSON dataclasses for UPF <-> MetaRPG subprocess communication.
Per planVer0.5.1 §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PROTOCOL_VERSION = 1


@dataclass
class BridgeRequest:
    """UPF -> MetaRPG bridge request."""

    command: str                  # "step" | "load" | "save"
    session_id: str
    player_text: str = ""
    language: str = "zh-CN"
    upf_context: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "command": self.command,
            "session_id": self.session_id,
            "player_text": self.player_text,
            "language": self.language,
            "upf_context": self.upf_context,
            "options": self.options,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeRequest":
        return cls(
            command=data.get("command", "step"),
            session_id=data.get("session_id", "default"),
            player_text=data.get("player_text", ""),
            language=data.get("language", "zh-CN"),
            upf_context=data.get("upf_context", {}),
            options=data.get("options", {}),
        )


@dataclass
class BridgeMessage:
    """One message in the response."""

    speaker: str    # "narrator" | "npc" | "system" | "debug"
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"speaker": self.speaker, "text": self.text}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeMessage":
        return cls(speaker=data.get("speaker", "system"), text=data.get("text", ""))


@dataclass
class BridgeApplyReport:
    """Lightweight apply report for the bridge."""

    applications: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    deferred: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "applications": self.applications,
            "rejected": self.rejected,
            "deferred": self.deferred,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeApplyReport":
        return cls(
            applications=data.get("applications", []),
            rejected=data.get("rejected", []),
            deferred=data.get("deferred", []),
        )


@dataclass
class BridgeSnapshot:
    """Player-visible world snapshot."""

    location: str = ""
    nearby_npcs: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    known_entities: list[str] = field(default_factory=list)
    active_hooks: list[str] = field(default_factory=list)
    frontiers: list[str] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "nearby_npcs": self.nearby_npcs,
            "facts": self.facts,
            "known_entities": self.known_entities,
            "active_hooks": self.active_hooks,
            "frontiers": self.frontiers,
            "relations": self.relations,
            "beliefs": self.beliefs,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeSnapshot":
        return cls(
            location=data.get("location", ""),
            nearby_npcs=data.get("nearby_npcs", []),
            facts=data.get("facts", []),
            known_entities=data.get("known_entities", []),
            active_hooks=data.get("active_hooks", []),
            frontiers=data.get("frontiers", []),
            relations=data.get("relations", []),
            beliefs=data.get("beliefs", []),
        )


@dataclass
class BridgeDebug:
    """Debug surface for playtest."""

    budget: str = ""
    touched_frontiers: list[str] = field(default_factory=list)
    top_affordances: list[str] = field(default_factory=list)
    plot_issues: list[str] = field(default_factory=list)
    active_hooks: list[str] = field(default_factory=list)
    claim_summary: list[tuple[str, str, str]] = field(default_factory=list)
    hypothesis_kind: str = ""
    hypothesis_confidence: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "touched_frontiers": self.touched_frontiers,
            "top_affordances": self.top_affordances,
            "plot_issues": self.plot_issues,
            "active_hooks": self.active_hooks,
            "claim_summary": self.claim_summary,
            "hypothesis_kind": self.hypothesis_kind,
            "hypothesis_confidence": self.hypothesis_confidence,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeDebug":
        return cls(
            budget=data.get("budget", ""),
            touched_frontiers=data.get("touched_frontiers", []),
            top_affordances=data.get("top_affordances", []),
            plot_issues=data.get("plot_issues", []),
            active_hooks=data.get("active_hooks", []),
            claim_summary=[tuple(x) for x in data.get("claim_summary", [])],
            hypothesis_kind=data.get("hypothesis_kind", ""),
            hypothesis_confidence=data.get("hypothesis_confidence", 0.0),
        )


@dataclass
class BridgeError:
    """Error payload."""

    code: str
    message: str

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeError":
        return cls(code=data.get("code", "unknown"), message=data.get("message", ""))


@dataclass
class BridgeResponse:
    """MetaRPG -> UPF bridge response."""

    ok: bool
    session_id: str = ""
    turn: int = 0
    messages: list[BridgeMessage] = field(default_factory=list)
    apply_report: BridgeApplyReport | None = None
    snapshot: BridgeSnapshot | None = None
    debug: BridgeDebug | None = None
    error: BridgeError | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "ok": self.ok,
            "session_id": self.session_id,
            "turn": self.turn,
            "messages": [m.to_json() for m in self.messages],
        }
        if self.apply_report:
            out["apply_report"] = self.apply_report.to_json()
        if self.snapshot:
            out["snapshot"] = self.snapshot.to_json()
        if self.debug:
            out["debug"] = self.debug.to_json()
        if self.error:
            out["error"] = self.error.to_json()
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BridgeResponse":
        return cls(
            ok=data.get("ok", False),
            session_id=data.get("session_id", ""),
            turn=data.get("turn", 0),
            messages=[BridgeMessage.from_json(m) for m in data.get("messages", [])],
            apply_report=BridgeApplyReport.from_json(data["apply_report"]) if "apply_report" in data else None,
            snapshot=BridgeSnapshot.from_json(data["snapshot"]) if "snapshot" in data else None,
            debug=BridgeDebug.from_json(data["debug"]) if "debug" in data else None,
            error=BridgeError.from_json(data["error"]) if "error" in data else None,
        )
