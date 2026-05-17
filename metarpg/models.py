"""Core data structures for MetaRPG v0.1.

Layers (per PLAN_SONNET §4):
- Hard canon: Fact, Knowledge
- Hot matrix: Relation, Motif, AvailableAction (plus a snapshot of facts/knowledge)
- Belief layer: Belief
- Compiled action: Action -> Patch (Effect list) -> ValidationResult
- Retrodiction: Retropath
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Fact:
    """A ground predicate, e.g. at(player, tavern). Hashable, set-friendly."""

    predicate: str
    args: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.predicate}({','.join(self.args)})"


@dataclass(frozen=True)
class Knowledge:
    """Agent knows a fact (epistemic, not necessarily true)."""

    agent: str
    fact: Fact

    def __str__(self) -> str:
        return f"{self.agent} knows {self.fact}"


@dataclass
class Relation:
    """Directed multi-dimensional relation, e.g. mara->player trust=.18 fear=.10."""

    from_agent: str
    to_agent: str
    dimensions: dict[str, float] = field(default_factory=dict)

    def get(self, dim: str, default: float = 0.0) -> float:
        return self.dimensions.get(dim, default)

    def update(self, dim: str, delta: float) -> None:
        cur = self.dimensions.get(dim, 0.0)
        self.dimensions[dim] = max(-1.0, min(1.0, cur + delta))


@dataclass
class Motif:
    """Active narrative motif, e.g. forbidden_place(old_mine) lure=.62 danger=.48."""

    name: str
    args: tuple[str, ...]
    params: dict[str, float] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, tuple[str, ...]]:
        return (self.name, self.args)


@dataclass(frozen=True)
class AvailableAction:
    """An action available on the player's frontier."""

    verb: str
    args: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.verb}({','.join(self.args)})"


@dataclass
class Belief:
    """Latent hypothesis with a probability in [0, 1]."""

    id: str
    description: str
    prob: float

    def clip(self) -> None:
        self.prob = max(0.0, min(1.0, self.prob))


@dataclass
class Effect:
    """One effect inside a patch.

    kind ∈ {event, observe, rel_delta, belief_delta, add_fact, remove_fact,
            add_knowledge, motif_delta}
    payload is a tuple whose shape depends on kind:
      event:         (event_name: str,)
      observe:       (observation: str,)
      rel_delta:     (from_agent, to_agent, dim, delta: float)
      belief_delta:  (belief_id_or_description: str, delta: float)
      add_fact:      (Fact,)
      remove_fact:   (Fact,)
      add_knowledge: (Knowledge,)
      motif_delta:   (motif_name, args_tuple, param_name, delta)
    """

    kind: str
    payload: tuple[Any, ...]


@dataclass
class Patch:
    """A structured proposed change derived from a player action."""

    intent: str
    requirements: list[str] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)


@dataclass
class Action:
    """Parsed player intent."""

    verb: str
    args: tuple[str, ...]
    text: str


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    failed_requirements: list[str] = field(default_factory=list)


@dataclass
class Retropath:
    """A proposed explanation chain for a high-confidence belief."""

    target: str  # belief description, e.g. "rusk_pressures_mara"
    causes: list[Fact] = field(default_factory=list)
    explains: list[str] = field(default_factory=list)


# ---------- v0.2 meta-act / claim validation models ----------


class ClaimStatus(Enum):
    """Five-level claim validation outcome (v0.2)."""

    ACCEPTED = "accepted"      # hard supported by canon/rules
    INFERRED = "inferred"      # weakly inferred by type/role/place/motif
    PROBABLE = "probable"      # plausible but uncertain; allowed for low-impact effects
    UNKNOWN = "unknown"        # not enough support; can still allow flavor, not hard canon
    REJECTED = "rejected"      # contradicts canon/rules


@dataclass
class MetaAct:
    """Raw player behavior plus local context. Not yet a game action."""

    raw_text: str
    actor: str
    turn: int
    local_entities: list[str] = field(default_factory=list)       # nearby NPCs, objects
    local_facts: list[Fact] = field(default_factory=list)         # small canon slice
    local_beliefs: list[Belief] = field(default_factory=list)     # relevant latent beliefs
    speech_fragments: list[str] = field(default_factory=list)     # quoted text
    surface_cues: list[str] = field(default_factory=list)         # extracted words/phrases
    player_location: str = ""                                     # current location


@dataclass
class Claim:
    """One validated claim with its outcome."""

    name: str
    args: tuple[str, ...]
    status: ClaimStatus
    reason: str = ""          # why this status was assigned


@dataclass
class ProposedEffect:
    """An effect proposed by a hypothesis, with impact level for filtering."""

    kind: str                 # event, observe, rel_delta, belief_delta, add_fact, ...
    payload: tuple[Any, ...]
    impact: int = 0           # 0=flavor, 1=social, 2=belief, 3=hard fact, 4=retro


@dataclass
class SubAct:
    """One sub-action inside a composite act hypothesis (v0.3)."""

    kind: str                 # e.g. "break_object", "threaten", "spill"
    actor: str
    args: tuple[str, ...] = field(default_factory=tuple)
    claims: list[Claim] = field(default_factory=list)
    effects: list[ProposedEffect] = field(default_factory=list)
    impact: int = 0           # 0=flavor, 1=social, 2=belief, 3=hard fact


@dataclass
class ActHypothesis:
    """Interpretation of what the player is trying to do."""

    act_kind: str
    confidence: float         # 0.0–1.0
    support_claims: list[Claim] = field(default_factory=list)
    intended_effects: list[ProposedEffect] = field(default_factory=list)
    risks: list[ProposedEffect] = field(default_factory=list)
    narration_intent: str = ""
    raw_text: str = ""        # original player input
    target: str = ""          # inferred target entity
    topic: str = ""           # inferred topic
    id: str = ""              # v0.3: unique hypothesis id
    subacts: list[SubAct] = field(default_factory=list)  # v0.3: composite decomposition
    rejected_reason: str | None = None  # v0.3: why the whole hypothesis was rejected


@dataclass
class EventHook:
    """v0.3.1: past event compiled into future trigger potential."""

    id: str
    owner: str = "player"
    source_turn: int = 0
    source_events: list[str] = field(default_factory=list)
    hook_type: str = "communicate"  # communicate / confront / investigate / emotion / leverage / return
    trigger_cues: list[str] = field(default_factory=list)
    valid_targets: list[str] = field(default_factory=list)
    payload_claims: list[Claim] = field(default_factory=list)
    proposed_effects: list[ProposedEffect] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    priority: float = 0.5
    ttl: int = 4
    consumed: bool = False
    decay_policy: str = "consume_once"  # consume_once / decay_each_turn / persistent_until_used


@dataclass
class WorldState:
    """Central runtime container — hot matrix + canon + beliefs."""

    turn: int = 0
    facts: set[Fact] = field(default_factory=set)
    knowledge: set[Knowledge] = field(default_factory=set)
    relations: dict[tuple[str, str], Relation] = field(default_factory=dict)
    motifs: dict[tuple[str, tuple[str, ...]], Motif] = field(default_factory=dict)
    frontier: list[AvailableAction] = field(default_factory=list)
    frontiers: dict = field(default_factory=dict)
    beliefs: dict[str, Belief] = field(default_factory=dict)
    archive_path: str = ""
    canon_log_path: str = ""

    # NPC catalog — agents that aren't the player
    npcs: set[str] = field(default_factory=set)
    locations: set[str] = field(default_factory=set)

    # v0.2 scenario tags for claim validation
    roles: dict[str, set[str]] = field(default_factory=dict)              # entity -> {role tags}
    place_services: dict[str, set[str]] = field(default_factory=dict)     # place -> {service tags}
    item_plausibility: dict[str, set[str]] = field(default_factory=dict)  # place -> {item tags}
    place_topics: dict[str, set[str]] = field(default_factory=dict)       # place -> {topic tags}

    # v0.3 object ontology — minimal tags for open-act validation
    object_tags: dict[str, set[str]] = field(default_factory=dict)        # obj -> {tag1, tag2}

    # v0.3.1 subject-bound event hooks
    hooks: dict[str, EventHook] = field(default_factory=dict)              # hook_id -> EventHook

    # v0.6.1 agentic turn continuity
    journal_notes: list[str] = field(default_factory=list)
    turn_event_log: list[str] = field(default_factory=list)

    def get_relation(self, a: str, b: str) -> Relation | None:
        return self.relations.get((a, b))

    def ensure_relation(self, a: str, b: str) -> Relation:
        key = (a, b)
        if key not in self.relations:
            self.relations[key] = Relation(a, b)
        return self.relations[key]


@dataclass
class LocalSlice:
    """The compressed view of WorldState restricted to touched entities."""

    touched: set[str]
    facts: list[Fact] = field(default_factory=list)
    knowledge: list[Knowledge] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    motifs: list[Motif] = field(default_factory=list)
    beliefs: list[Belief] = field(default_factory=list)
    frontier: list[AvailableAction] = field(default_factory=list)
