"""Bridge session — v0.5.1.

Load/create/save sessions by id for the UPF bridge.
Session = WorldState + turn + recent messages + frontier registry.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .models import WorldState
from .scenarios.greyfen import build


DEFAULT_SESSION_DIR = "runtime/bridge_sessions"


def _session_path(session_id: str, base_dir: str = DEFAULT_SESSION_DIR) -> str:
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{session_id}.json")


def load_or_create_session(session_id: str, base_dir: str = DEFAULT_SESSION_DIR) -> tuple[WorldState, list[dict[str, Any]], int]:
    """Load existing session or create a new Greyfen one.

    Returns (world, messages, turn).
    """
    path = _session_path(session_id, base_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        world = _world_from_blob(blob.get("world", {}))
        messages = blob.get("messages", [])
        turn = blob.get("turn", 0)
        world.turn = turn
        return world, messages, turn

    # New session
    world = build(archive_path="", canon_log_path="")
    return world, [], 0


def save_session(
    session_id: str,
    world: WorldState,
    messages: list[dict[str, Any]],
    base_dir: str = DEFAULT_SESSION_DIR,
) -> None:
    """Persist session to disk."""
    path = _session_path(session_id, base_dir)
    blob = {
        "session_id": session_id,
        "turn": world.turn,
        "world": _world_to_blob(world),
        "messages": messages,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False, indent=2, default=_json_default)


def _world_to_blob(world: WorldState) -> dict[str, Any]:
    """Serialize WorldState to a JSON-friendly dict."""
    from .models import Fact, Knowledge, Relation, Motif, Belief, AvailableAction

    def fact_to_dict(f: Fact) -> dict[str, Any]:
        return {"predicate": f.predicate, "args": list(f.args)}

    def knowledge_to_dict(k: Knowledge) -> dict[str, Any]:
        return {"agent": k.agent, "fact": fact_to_dict(k.fact)}

    def relation_to_dict(r: Relation) -> dict[str, Any]:
        return {"from": r.from_agent, "to": r.to_agent, "dimensions": r.dimensions}

    def motif_to_dict(m: Motif) -> dict[str, Any]:
        return {"name": m.name, "args": list(m.args), "params": m.params}

    def belief_to_dict(b: Belief) -> dict[str, Any]:
        return {"id": b.id, "description": b.description, "prob": b.prob}

    def frontier_to_dict(f: AvailableAction) -> dict[str, Any]:
        return {"verb": f.verb, "args": list(f.args)}

    blob: dict[str, Any] = {
        "turn": world.turn,
        "facts": [fact_to_dict(f) for f in world.facts],
        "knowledge": [knowledge_to_dict(k) for k in world.knowledge],
        "relations": {f"{k[0]}->{k[1]}": relation_to_dict(v) for k, v in world.relations.items()},
        "motifs": {f"{k[0]}({','.join(k[1])})": motif_to_dict(v) for k, v in world.motifs.items()},
        "beliefs": {k: belief_to_dict(v) for k, v in world.beliefs.items()},
        "frontier": [frontier_to_dict(f) for f in world.frontier],
        "npcs": sorted(world.npcs),
        "locations": sorted(world.locations),
        "roles": {k: sorted(v) for k, v in world.roles.items()},
        "place_services": {k: sorted(v) for k, v in world.place_services.items()},
        "item_plausibility": {k: sorted(v) for k, v in world.item_plausibility.items()},
        "place_topics": {k: sorted(v) for k, v in world.place_topics.items()},
        "object_tags": {k: sorted(v) for k, v in world.object_tags.items()},
    }

    # v0.3.1 hooks
    if hasattr(world, "hooks") and world.hooks:
        from .models import EventHook
        def hook_to_dict(h: EventHook) -> dict[str, Any]:
            return {
                "id": h.id,
                "owner": h.owner,
                "source_turn": h.source_turn,
                "source_events": h.source_events,
                "hook_type": h.hook_type,
                "trigger_cues": h.trigger_cues,
                "valid_targets": h.valid_targets,
                "topics": h.topics,
                "places": h.places,
                "participants": h.participants,
                "priority": h.priority,
                "ttl": h.ttl,
                "consumed": h.consumed,
                "decay_policy": h.decay_policy,
            }
        blob["hooks"] = {k: hook_to_dict(v) for k, v in world.hooks.items()}

    # v0.5 frontiers
    if hasattr(world, "frontiers") and world.frontiers:
        from .frontier import Frontier
        def v5frontier_to_dict(f: Frontier) -> dict[str, Any]:
            return {
                "id": f.id,
                "kind": f.kind.value,
                "anchor_entity": f.anchor_entity,
                "location": f.location,
                "source_event": f.source_event,
                "status": f.status.value,
                "salience": f.salience,
                "uncertainty": f.uncertainty,
                "expected_reuse": f.expected_reuse,
                "risk": f.risk,
                "budget_hint": f.budget_hint,
                "created_turn": f.created_turn,
                "last_touched_turn": f.last_touched_turn,
                "metadata": f.metadata,
            }
        blob["frontiers"] = {k: v5frontier_to_dict(v) for k, v in world.frontiers.items()}

    return blob


def _world_from_blob(blob: dict[str, Any]) -> WorldState:
    """Deserialize WorldState from a JSON blob."""
    from .models import Fact, Knowledge, Relation, Motif, Belief, AvailableAction

    w = WorldState()
    w.turn = blob.get("turn", 0)
    w.facts = {Fact(f["predicate"], tuple(f["args"])) for f in blob.get("facts", [])}
    w.knowledge = {
        Knowledge(k["agent"], Fact(k["fact"]["predicate"], tuple(k["fact"]["args"])))
        for k in blob.get("knowledge", [])
    }
    w.relations = {}
    for key, r in blob.get("relations", {}).items():
        parts = key.split("->", 1)
        if len(parts) == 2:
            w.relations[(parts[0], parts[1])] = Relation(r["from"], r["to"], dict(r.get("dimensions", {})))
    w.motifs = {}
    for key, m in blob.get("motifs", {}).items():
        # Simple parse: name(args...)
        if "(" in key and key.endswith(")"):
            name = key[:key.index("(")]
            args_str = key[key.index("(")+1:-1]
            args = tuple(args_str.split(",")) if args_str else ()
            w.motifs[(name, args)] = Motif(name, args, dict(m.get("params", {})))
    w.beliefs = {}
    for bid, b in blob.get("beliefs", {}).items():
        w.beliefs[bid] = Belief(b["id"], b["description"], b.get("prob", 0.5))
    w.frontier = [AvailableAction(f["verb"], tuple(f["args"])) for f in blob.get("frontier", [])]
    w.npcs = set(blob.get("npcs", []))
    w.locations = set(blob.get("locations", []))
    w.roles = {k: set(v) for k, v in blob.get("roles", {}).items()}
    w.place_services = {k: set(v) for k, v in blob.get("place_services", {}).items()}
    w.item_plausibility = {k: set(v) for k, v in blob.get("item_plausibility", {}).items()}
    w.place_topics = {k: set(v) for k, v in blob.get("place_topics", {}).items()}
    w.object_tags = {k: set(v) for k, v in blob.get("object_tags", {}).items()}

    # v0.3.1 hooks
    if "hooks" in blob:
        from .models import EventHook, Claim, ProposedEffect
        for hid, h in blob["hooks"].items():
            hook = EventHook(
                id=h.get("id", hid),
                owner=h.get("owner", "player"),
                source_turn=h.get("source_turn", 0),
                source_events=h.get("source_events", []),
                hook_type=h.get("hook_type", "communicate"),
                trigger_cues=h.get("trigger_cues", []),
                valid_targets=h.get("valid_targets", []),
                topics=h.get("topics", []),
                places=h.get("places", []),
                participants=h.get("participants", []),
                priority=h.get("priority", 0.5),
                ttl=h.get("ttl", 4),
                consumed=h.get("consumed", False),
                decay_policy=h.get("decay_policy", "consume_once"),
            )
            w.hooks[hid] = hook

    # v0.5 frontiers
    if "frontiers" in blob:
        from .frontier import Frontier as V5Frontier, FrontierKind, FrontierStatus
        for fid, f in blob["frontiers"].items():
            try:
                kind = FrontierKind(f.get("kind", "scene_boundary"))
            except ValueError:
                kind = FrontierKind.SCENE_BOUNDARY
            try:
                status = FrontierStatus(f.get("status", "compressed"))
            except ValueError:
                status = FrontierStatus.COMPRESSED
            vf = V5Frontier(
                id=f.get("id", fid),
                kind=kind,
                anchor_entity=f.get("anchor_entity", ""),
                location=f.get("location", ""),
                source_event=f.get("source_event", ""),
                status=status,
                salience=f.get("salience", 0.5),
                uncertainty=f.get("uncertainty", 0.5),
                expected_reuse=f.get("expected_reuse", 0.5),
                risk=f.get("risk", 0.0),
                budget_hint=f.get("budget_hint", "small"),
                created_turn=f.get("created_turn", 0),
                last_touched_turn=f.get("last_touched_turn", 0),
                metadata=f.get("metadata", {}),
            )
            w.frontiers[fid] = vf

    return w


def _json_default(obj: Any) -> Any:
    """Fallback JSON encoder for custom types."""
    if hasattr(obj, "to_json"):
        return obj.to_json()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
