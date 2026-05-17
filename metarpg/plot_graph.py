"""PLOTTER-inspired graph layer — v0.4.

Builds and maintains structural graphs from admitted events and world state.
Minimum viable: extraction first, algorithms later.

Graph types:
  EventGraph     — admitted events as nodes, causal/social edges
  CharacterGraph — NPC/player snapshots, knowledge, tensions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .apply_report import ApplyReport
from .models import WorldState


# ---------- nodes ----------


@dataclass
class EventNode:
    """One admitted event in the narrative graph."""

    id: str
    turn: int
    kind: str
    participants: list[str] = field(default_factory=list)
    location: str = ""
    topics: list[str] = field(default_factory=list)
    source_events: list[str] = field(default_factory=list)
    source_hook: str = ""
    admitted: bool = True


@dataclass
class CharacterNode:
    """One character snapshot in the character graph."""

    id: str
    traits: list[str] = field(default_factory=list)
    current_location: str = ""
    known_facts: list[str] = field(default_factory=list)
    active_hooks: list[str] = field(default_factory=list)
    emotional_state: dict[str, float] = field(default_factory=dict)
    recent_event_ids: list[str] = field(default_factory=list)


# ---------- edges ----------


@dataclass
class GraphEdge:
    """Typed edge between graph nodes."""

    source: str
    target: str
    relation: str  # "causes", "reveals", "motivates", "blocks", "knows", "tensions"
    weight: float = 1.0


# ---------- graphs ----------


@dataclass
class EventGraph:
    """Structural graph of admitted narrative events."""

    events: dict[str, EventNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add(self, node: EventNode) -> None:
        self.events[node.id] = node

    def link(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> None:
        if source_id in self.events and target_id in self.events:
            self.edges.append(GraphEdge(source_id, target_id, relation, weight))

    def children(self, event_id: str, relation: str = "") -> list[EventNode]:
        """Return events directly caused by or linked to event_id."""
        result: list[EventNode] = []
        for e in self.edges:
            if e.source == event_id and (not relation or e.relation == relation):
                result.append(self.events[e.target])
        return result

    def parents(self, event_id: str, relation: str = "") -> list[EventNode]:
        """Return events that directly cause or link to event_id."""
        result: list[EventNode] = []
        for e in self.edges:
            if e.target == event_id and (not relation or e.relation == relation):
                result.append(self.events[e.source])
        return result

    def orphans(self) -> list[EventNode]:
        """Events with no incoming or outgoing edges."""
        connected = set()
        for e in self.edges:
            connected.add(e.source)
            connected.add(e.target)
        return [n for nid, n in self.events.items() if nid not in connected]


@dataclass
class CharacterGraph:
    """Structural graph of characters and their relationships."""

    characters: dict[str, CharacterNode] = field(default_factory=dict)
    tensions: list[GraphEdge] = field(default_factory=list)

    def add(self, node: CharacterNode) -> None:
        self.characters[node.id] = node

    def tension(self, a: str, b: str, topic: str, weight: float = 1.0) -> None:
        self.tensions.append(GraphEdge(a, b, f"tensions:{topic}", weight))


# ---------- builders ----------


def build_event_graph(world: WorldState, report: ApplyReport | None) -> EventGraph:
    """Build an EventGraph from the latest ApplyReport."""
    graph = EventGraph()
    if report is None:
        return graph

    # Add applied events as nodes
    for i, (event, delta) in enumerate(report.applied):
        node_id = f"E{world.turn}_{i}"
        participants = _extract_participants(event)
        node = EventNode(
            id=node_id,
            turn=world.turn,
            kind=event.kind,
            participants=participants,
            location=_location_of(world, "player"),
            topics=_extract_topics(event),
            source_events=[str(e) for e in delta.get("events", [])],
            source_hook=event.source if event.source.startswith("hook:") else "",
            admitted=True,
        )
        graph.add(node)

        # Link to previous events on same topic (simple causal chaining)
        for prev_id, prev in graph.events.items():
            if prev_id == node_id:
                continue
            if set(prev.topics) & set(node.topics):
                graph.link(prev_id, node_id, "causes", 0.5)

    # Add rejected events as nodes (marked not admitted)
    for i, (event, reason) in enumerate(report.rejected):
        node_id = f"R{world.turn}_{i}"
        node = EventNode(
            id=node_id,
            turn=world.turn,
            kind=event.kind,
            participants=_extract_participants(event),
            location=_location_of(world, "player"),
            admitted=False,
        )
        graph.add(node)

    return graph


def build_character_graph(world: WorldState) -> CharacterGraph:
    """Build a CharacterGraph snapshot from current WorldState."""
    graph = CharacterGraph()

    for npc in world.npcs:
        node = CharacterNode(id=npc)

        # Location
        for f in world.facts:
            if f.predicate == "at" and len(f.args) == 2 and f.args[0] == npc:
                node.current_location = f.args[1]

        # Known facts
        for k in world.knowledge:
            if k.agent == npc:
                node.known_facts.append(str(k.fact))

        # Active hooks involving this character
        for hook in world.hooks.values():
            if npc in hook.valid_targets or npc in hook.participants:
                node.active_hooks.append(hook.id)

        # Emotional state from relations
        for (_, _), rel in world.relations.items():
            if rel.from_agent == npc:
                for dim, val in rel.dimensions.items():
                    node.emotional_state[dim] = val

        graph.add(node)

    # Tensions from motifs
    for (mname, margs), motif in world.motifs.items():
        if mname == "debtor_creditor" and len(margs) == 2:
            a, b = margs[0], margs[1]
            pressure = motif.params.get("pressure", 0.0)
            if pressure > 0.3:
                graph.tension(a, b, "debt_pressure", pressure)
        elif mname == "forbidden_place" and len(margs) == 1:
            place = margs[0]
            for char in graph.characters.values():
                if char.current_location == place:
                    for other in graph.characters.values():
                        if other.id != char.id:
                            graph.tension(char.id, other.id, f"forbidden:{place}", 0.4)

    return graph


# ---------- utilities ----------


def _extract_participants(event) -> list[str]:
    """Heuristic extraction of participants from event payload."""
    p = event.payload
    participants: set[str] = set()
    for item in p:
        if isinstance(item, str) and item not in ("player", ""):
            participants.add(item)
        elif hasattr(item, "args"):
            for arg in item.args:
                if isinstance(arg, str) and arg not in ("player", ""):
                    participants.add(arg)
    return sorted(participants)


def _extract_topics(event) -> list[str]:
    """Heuristic extraction of topics from event kind and payload."""
    topics: set[str] = set()
    p = event.payload
    for item in p:
        if isinstance(item, str):
            # Simple keyword topics
            if any(k in item for k in ("mine", "old_mine", "矿")):
                topics.add("mine")
            if any(k in item for k in ("rusk", "拉斯克")):
                topics.add("rusk")
            if any(k in item for k in ("mara", "玛拉")):
                topics.add("mara")
            if any(k in item for k in ("iven", "艾文")):
                topics.add("iven")
    return sorted(topics)


def _location_of(world: WorldState, entity: str) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == entity:
            return f.args[1]
    return ""
