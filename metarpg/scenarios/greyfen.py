"""Greyfen village mystery — initial state + hooks for v0.1.

Per PLAN_SONNET §3. Three NPCs, four+1 locations, an unresolved mine entry, and
five latent hypotheses awaiting evidence.

All scenario-specific logic (topic impacts, combo listeners, retropath templates,
dynamic frontier) is registered through ScenarioHooks so the engine stays generic.
"""
from __future__ import annotations

from ..models import (
    AvailableAction,
    Belief,
    Effect,
    Fact,
    Knowledge,
    Motif,
    Patch,
    Relation,
    Retropath,
    WorldState,
)
from ..frontier import Frontier as V5Frontier, FrontierKind, FrontierStatus
from ..scenario_hooks import ScenarioHooks


# ---------- topic impacts (ask / confront about topics) ----------

_GREYFEN_TOPIC_IMPACTS: dict[tuple[str, str], list[tuple[str, float]]] = {
    ("ask", "mine"): [
        ("mara_knows_recent_entry", 0.10),
        ("mara_entered_mine", 0.04),
        ("rusk_pressures_mara", 0.05),
    ],
    ("ask", "old_mine"): [
        ("mara_knows_recent_entry", 0.10),
        ("mara_entered_mine", 0.04),
        ("rusk_pressures_mara", 0.05),
    ],
    ("ask", "iven"): [
        ("iven_alive_in_mine", 0.06),
        ("iven_dead_and_hidden", 0.04),
    ],
    ("confront", "mine"): [
        ("mara_knows_recent_entry", 0.20),
        ("rusk_pressures_mara", 0.10),
    ],
    ("confront", "old_mine"): [
        ("mara_knows_recent_entry", 0.20),
        ("rusk_pressures_mara", 0.10),
    ],
}


# ---------- custom action compilers (scenario-specific overrides) ----------

def _compile_listen_greyfen(action, world, hooks) -> Patch:
    """Greyfen-specific listen: overhearing Rusk + Mara yields big belief updates."""
    targets = [t for t in action.args if t]
    patch = Patch(intent=f"listen(player,{','.join(targets) or 'silence'})")
    if not targets:
        patch.effects.append(Effect("event", ("player_listened_to_silence",)))
        return patch
    for t in targets:
        patch.requirements.append(f"same_location(player,{t})")
    patch.effects.append(Effect("event", (f"player_listened_to_{'_and_'.join(targets)}",)))
    # Greyfen combo: Rusk + Mara conversation
    target_set = set(targets)
    if {"rusk", "mara"}.issubset(target_set):
        patch.effects.append(Effect("belief_delta", ("rusk_pressures_mara", 0.35)))
        patch.effects.append(Effect("belief_delta", ("mara_knows_recent_entry", 0.25)))
        patch.effects.append(Effect("belief_delta", ("mara_ignorant_about_mine", -0.30)))
        patch.effects.append(Effect("observe", ("rusk_warning_mara_about_outsiders",)))
    return patch


# ---------- retropath templates ----------

_GREYFEN_RETRO_TEMPLATES: dict[str, Retropath] = {
    "mara_knows_recent_entry": Retropath(
        target="mara_knows_recent_entry",
        causes=[Fact("saw", ("mara", "recent_entry", "day_minus_2"))],
        explains=["mara_evasive_about_mine"],
    ),
    "mara_entered_mine": Retropath(
        target="mara_entered_mine",
        causes=[
            Fact("found_passage", ("mara", "old_mine")),
            Fact("entered", ("mara", "old_mine", "day_minus_2")),
        ],
        explains=["mara_evasive_about_mine", "mara_knows_recent_entry"],
    ),
    "rusk_pressures_mara": Retropath(
        target="rusk_pressures_mara",
        causes=[
            Fact("mara_saw_rusk_near_mine", ("day_minus_2",)),
            Fact("rusk_threatened_mara", ("day_minus_1",)),
        ],
        explains=["mara_evasive_about_mine"],
    ),
    "iven_alive_in_mine": Retropath(
        target="iven_alive_in_mine",
        causes=[
            Fact("alive", ("iven",)),
            Fact("found_passage", ("iven", "old_mine")),
            Fact("entered", ("iven", "old_mine", "day_minus_3")),
        ],
        explains=["missing(iven)"],
    ),
    "iven_dead_and_hidden": Retropath(
        target="iven_dead_and_hidden",
        causes=[
            Fact("dead", ("iven",)),
            Fact("hidden_body", ("iven", "old_mine")),
        ],
        explains=["missing(iven)"],
    ),
}


# ---------- dynamic frontier generator ----------

def _current_location(world: WorldState) -> str:
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2 and f.args[0] == "player":
            return f.args[1]
    return ""


def _npcs_at(world: WorldState, loc: str) -> list[str]:
    out: list[str] = []
    for f in world.facts:
        if f.predicate == "at" and len(f.args) == 2:
            entity, place = f.args[0], f.args[1]
            if entity != "player" and place == loc and entity in world.npcs:
                out.append(entity)
    return out


def _generate_frontier(world: WorldState) -> list[AvailableAction]:
    """Dynamic frontier: available actions depend on player location + world state.

    Also populates world.frontiers with v0.5 frontier registry entries.
    """
    loc = _current_location(world)
    nearby = _npcs_at(world, loc)
    actions: list[AvailableAction] = []
    # Preserve existing frontiers (e.g. test-seeded or scenario initial)
    frontiers: dict[str, V5Frontier] = dict(getattr(world, "frontiers", {}))
    _fid = len([k for k in frontiers if k.startswith("F_greyfen_")])

    def _add(kind, anchor, location, source, salience=0.5, uncertainty=0.5, budget="small"):
        nonlocal _fid
        # Deduplicate by kind + anchor + source_event
        for existing in frontiers.values():
            if existing.kind == kind and existing.anchor_entity == anchor and existing.source_event == source:
                return
        _fid += 1
        fid = f"F_greyfen_{_fid}"
        frontiers[fid] = V5Frontier(
            id=fid,
            kind=kind,
            anchor_entity=anchor,
            location=location,
            source_event=source,
            status=FrontierStatus.COMPRESSED,
            salience=salience,
            uncertainty=uncertainty,
            budget_hint=budget,
        )

    # Movement
    for place in world.locations:
        if place != loc and place != "old_mine":
            actions.append(AvailableAction("go", (place,)))
            _add(FrontierKind.SCENE_BOUNDARY, place, loc, f"go_{place}", salience=0.4)
    if loc == "old_mine_gate":
        actions.append(AvailableAction("sneak", ("old_mine",)))
        _add(FrontierKind.THREAT_BOUNDARY, "old_mine", loc, "sneak_old_mine", salience=0.6, uncertainty=0.7, budget="medium")

    # NPC interactions
    for npc in nearby:
        actions.append(AvailableAction("ask", (npc, "mine")))
        _add(FrontierKind.UNQUERIED_NPC, npc, loc, f"ask_{npc}_mine", salience=0.6)
        actions.append(AvailableAction("observe", (npc,)))
        _add(FrontierKind.SALIENT_OBJECT, npc, loc, f"observe_{npc}", salience=0.5)
        actions.append(AvailableAction("help", (npc,)))
        _add(FrontierKind.UNRESOLVED_GOAL, npc, loc, f"help_{npc}", salience=0.5)
        if npc == "mara":
            actions.append(AvailableAction("ask", (npc, "iven")))
            _add(FrontierKind.UNKNOWN_CAUSAL_PATH, npc, loc, "ask_mara_iven", salience=0.55, uncertainty=0.6)
            mara_knows = world.beliefs.get("H1")
            if mara_knows and mara_knows.prob >= 0.50:
                actions.append(AvailableAction("confront", (npc, "mine")))
                _add(FrontierKind.ACTIVE_SOCIAL_TENSION, npc, loc, "confront_mara_mine", salience=0.7, uncertainty=0.5, budget="medium")

    # Listen combos (only when multiple NPCs present)
    if len(nearby) >= 2:
        actions.append(AvailableAction("listen", tuple(nearby)))
        _add(FrontierKind.LATENT_HOOK, "group_listen", loc, "listen_group", salience=0.45)

    world.frontiers = frontiers
    return actions


# ---------- public API ----------

def build_hooks() -> ScenarioHooks:
    """Return all Greyfen-specific extensions for the engine."""
    return ScenarioHooks(
        topic_impacts=dict(_GREYFEN_TOPIC_IMPACTS),
        action_compilers={"listen": _compile_listen_greyfen},
        retrodict_templates=dict(_GREYFEN_RETRO_TEMPLATES),
        frontier_generator=_generate_frontier,
    )


def build(archive_path: str = "", canon_log_path: str = "") -> WorldState:
    w = WorldState(archive_path=archive_path, canon_log_path=canon_log_path)
    w.npcs = {"mara", "rusk", "iven"}
    w.locations = {"tavern", "old_mine_gate", "guard_post", "mara_cellar", "old_mine"}

    # v0.2 scenario tags for claim validation
    w.roles = {
        "mara": {"bartender", "bartender_service", "tavern_keeper", "service"},
        "rusk": {"guard", "guard_captain", "security"},
        "iven": {"miner"},
    }
    w.place_services = {
        "tavern": {"drink_service", "food_service", "social_hub"},
        "guard_post": {"security", "information"},
        "old_mine_gate": {"access_control"},
        "mara_cellar": {"storage"},
    }
    w.item_plausibility = {
        "tavern": {"ale", "mug", "chair", "table", "lantern", "bread"},
        "old_mine_gate": {"loose_stone", "pickaxe", "rope", "lantern", "debris"},
        "guard_post": {"spear", "torch", "papers", "chair"},
        "mara_cellar": {"barrel", "crate", "lantern"},
    }
    w.place_topics = {
        "tavern": {"local_news", "mine", "iven", "ale", "gossip", "service"},
        "guard_post": {"mine", "security", "iven", "local_news"},
        "old_mine_gate": {"mine", "seal", "loose_stone", "access"},
        "mara_cellar": {"storage", "mine"},
    }

    # v0.3 minimal object tags for open-act validation
    w.object_tags = {
        "ale_mug": {"fragile", "container", "movable"},
        "ale": {"liquid"},
        "bottle": {"fragile", "container", "movable"},
        "chair": {"movable", "rigid"},
        "table": {"rigid"},
        "candle": {"flammable", "movable"},
        "rag": {"movable", "absorbent"},
        "map": {"paper", "fragile", "information_object"},
        "loose_stone": {"rigid", "movable", "throwable"},
        "debris": {"rigid"},
        "rope": {"flexible", "movable"},
        "old_door": {"rigid", "blocks_path"},
        "seal_chain": {"rigid", "locked"},
        "spear": {"sharp", "weapon"},
        "papers": {"information_object"},
        "torch": {"fire_source", "movable"},
        "glass_shard": {"sharp", "movable"},
    }

    # Hard canon
    w.facts.update({
        Fact("at", ("player", "tavern")),
        Fact("at", ("mara", "tavern")),
        Fact("at", ("rusk", "guard_post")),
        Fact("sealed", ("old_mine",)),
        Fact("missing", ("iven",)),
        Fact("said", ("mara", "the_mine_is_sealed")),
    })

    # Knowledge partitions
    w.knowledge.update({
        Knowledge("mara", Fact("sealed", ("old_mine",))),
        Knowledge("rusk", Fact("sealed", ("old_mine",))),
        Knowledge("mara", Fact("missing", ("iven",))),
        Knowledge("rusk", Fact("missing", ("iven",))),
    })

    # Relations
    w.relations[("mara", "player")] = Relation(
        "mara", "player", {"trust": 0.18, "fear": 0.10, "curiosity": 0.35}
    )
    w.relations[("rusk", "player")] = Relation(
        "rusk", "player", {"trust": 0.10, "fear": 0.05}
    )
    w.relations[("mara", "rusk")] = Relation(
        "mara", "rusk", {"fear": 0.40, "trust": 0.30}
    )
    w.relations[("rusk", "mara")] = Relation(
        "rusk", "mara", {"trust": 0.20, "control": 0.55}
    )

    # Motifs
    w.motifs[("forbidden_place", ("old_mine",))] = Motif(
        name="forbidden_place",
        args=("old_mine",),
        params={"lure": 0.62, "danger": 0.48, "salience": 0.40},
    )
    w.motifs[("debtor_creditor", ("mara", "rusk"))] = Motif(
        name="debtor_creditor",
        args=("mara", "rusk"),
        params={"pressure": 0.55, "due": 0.70},
    )

    # Frontier (initial — will be regenerated each turn by hooks)
    w.frontier = [
        AvailableAction("ask", ("mara", "old_mine")),
        AvailableAction("sneak", ("old_mine_gate",)),
        AvailableAction("confront", ("rusk", "mara")),
        AvailableAction("go", ("guard_post",)),
        AvailableAction("help", ("mara",)),
    ]
    # Seed v0.5 frontiers
    w.frontiers = {
        "F_greyfen_ask_mara": V5Frontier(
            id="F_greyfen_ask_mara",
            kind=FrontierKind.UNQUERIED_NPC,
            anchor_entity="mara",
            location="tavern",
            source_event="ask_mara_old_mine",
            status=FrontierStatus.COMPRESSED,
            salience=0.6,
        ),
        "F_greyfen_sneak": V5Frontier(
            id="F_greyfen_sneak",
            kind=FrontierKind.THREAT_BOUNDARY,
            anchor_entity="old_mine_gate",
            location="tavern",
            source_event="sneak_old_mine",
            status=FrontierStatus.COMPRESSED,
            salience=0.5,
        ),
        "F_greyfen_confront": V5Frontier(
            id="F_greyfen_confront",
            kind=FrontierKind.ACTIVE_SOCIAL_TENSION,
            anchor_entity="rusk",
            location="tavern",
            source_event="confront_rusk_mara",
            status=FrontierStatus.COMPRESSED,
            salience=0.7,
        ),
        "F_greyfen_go_guard": V5Frontier(
            id="F_greyfen_go_guard",
            kind=FrontierKind.SCENE_BOUNDARY,
            anchor_entity="guard_post",
            location="tavern",
            source_event="go_guard_post",
            status=FrontierStatus.COMPRESSED,
            salience=0.4,
        ),
        "F_greyfen_help": V5Frontier(
            id="F_greyfen_help",
            kind=FrontierKind.UNRESOLVED_GOAL,
            anchor_entity="mara",
            location="tavern",
            source_event="help_mara",
            status=FrontierStatus.COMPRESSED,
            salience=0.5,
        ),
    }

    # Beliefs
    w.beliefs = {
        "H1": Belief("H1", "mara_knows_recent_entry", 0.45),
        "H2": Belief("H2", "mara_entered_mine", 0.18),
        "H3": Belief("H3", "rusk_pressures_mara", 0.35),
        "H4": Belief("H4", "iven_alive_in_mine", 0.30),
        "H5": Belief("H5", "iven_dead_and_hidden", 0.20),
        "H6": Belief("H6", "mara_ignorant_about_mine", 0.30),
    }

    return w
