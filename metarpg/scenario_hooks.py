"""Scenario-specific extension hooks.

A scenario registers:
- topic impacts: which beliefs change when asking/confronting about topics
- action compilers: how to turn parsed actions into patches (overrides defaults)
- retropath templates: what cause chains to propose when beliefs cross threshold
- frontier generator: what actions are available given current world state

The engine is scenario-agnostic; all scenario-specific logic lives in hooks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .models import Action, AvailableAction, Patch, Retropath, WorldState

# compiler signature: fn(action, world, hooks) -> Patch
ActionCompiler = Callable[[Action, WorldState, "ScenarioHooks"], Patch]

# frontier generator signature: fn(world) -> list[AvailableAction]
FrontierGenerator = Callable[[WorldState], list[AvailableAction]]


@dataclass
class ScenarioHooks:
    topic_impacts: dict[tuple[str, str], list[tuple[str, float]]] = field(
        default_factory=dict
    )
    action_compilers: dict[str, ActionCompiler] = field(default_factory=dict)
    retrodict_templates: dict[str, Retropath] = field(default_factory=dict)
    frontier_generator: FrontierGenerator | None = None
