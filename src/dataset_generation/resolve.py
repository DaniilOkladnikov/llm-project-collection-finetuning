"""Bind a task's variables to a concrete scene, gate compatibility, and seed a
random initial state (DSL request steps 1 & 2).

Variable resolution and the pose/observe lookups reuse
``finetuning.variable_resolver``; the random object/robot state reuses
``tool_simulation_server.state_resolver.StateResolver``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from tool_simulation_server.scene import SceneConfig
from tool_simulation_server.state_resolver import StateResolver

from finetuning.variable_resolver import VariableResolver
from finetuning.models import VariableType

from dataset_generation.context import Binding, Role, SceneView
from dataset_generation.dsl_state import DslState
from dataset_generation.sim_driver import SimDriver
from dataset_generation.taskspec import TaskSpec


class IncompatibleScenario(Exception):
    """The task cannot be satisfied on this scene; skip and count it."""


@dataclass
class SceneCaps:
    full_pick: bool
    full_place: bool
    full_observe: bool
    has_home: bool


def scene_capabilities(view: SceneView) -> SceneCaps:
    types = list(view.config.object_types)
    locs = view.object_locations
    full_pick = all(view.pick_pose(t, l) for t in types for l in locs)
    full_place = all(view.place_pose(t, l) for t in types for l in locs)
    full_observe = bool(view.observe_poses) and all(l in view.covering_poses for l in locs)
    return SceneCaps(full_pick, full_place, full_observe,
                     has_home="home" in view.config.positions)


def build_binding(task: TaskSpec, config: SceneConfig, view: SceneView,
                  seed: int) -> Binding:
    resolver = VariableResolver(config, seed)
    try:
        resolved = resolver.resolve_all(task.variables)
    except ValueError as e:
        raise IncompatibleScenario(str(e))

    roles: Dict[str, Role] = {}
    for var in task.variables:
        name = var.name.lstrip("$")
        value = resolved[var.name]
        if var.type == VariableType.OBJECT_TYPE:
            roles[name] = Role(name=name, phrase=value, is_target=False, value=value)
        else:
            locations = view.expand(value)
            if not locations:
                raise IncompatibleScenario(f"target {name}={value} has no locations")
            is_collection = value in view.collections
            roles[name] = Role(name=name, phrase=value, is_target=True,
                               locations=locations, is_collection=is_collection)
    return Binding(roles)


def check_compatibility(task: TaskSpec, binding: Binding, view: SceneView,
                        caps: SceneCaps) -> None:
    uses_pick, uses_place = task.program.uses()
    if uses_pick and not caps.full_pick:
        raise IncompatibleScenario("scene lacks full pick-pose coverage")
    if uses_place and not caps.full_place:
        raise IncompatibleScenario("scene lacks full place-pose coverage")
    if not caps.full_observe:
        raise IncompatibleScenario("scene lacks full observe coverage")

    # every target location must be observable
    for role in binding.roles.values():
        if role.is_target:
            for loc in role.locations:
                if loc not in view.covering_poses:
                    raise IncompatibleScenario(f"{loc} is not observable")


def held_type_for(task: TaskSpec, binding: Binding, rng) -> Optional[str]:
    """The object type the robot starts holding (DSL request step 2)."""
    if task.held in (None,):
        return None
    if task.held == "any":
        return rng.choice(list(binding_types(binding)) or [None])
    return binding.type_value(task.held) if task.held in binding else None


def binding_types(binding: Binding):
    # all distinct object types referenced by the binding's type roles
    return {r.value for r in binding.roles.values() if not r.is_target and r.value}


def build_initial_dsl_state(held_type: Optional[str]) -> DslState:
    """STATE the model starts the turn with.

    When the prompt establishes the robot is holding something, the model writes
    that directly (DSL §3.1 user-stated change).
    """
    state = DslState()
    if held_type is not None:
        state.held = held_type
        state.gripper = "closed"
    return state


def make_state_def(held_type: Optional[str], view: SceneView,
                   scene_types: List[str]) -> Dict:
    """Random initial scene state for the simulator (StateResolver rules)."""
    max_objects = len(view.object_locations)
    scatter = {"min_objects": 0, "max_objects": max_objects,
               "location_pattern": "*", "type_pattern": "*"}

    if held_type is not None:
        return {
            "robot": {"position": ["*"], "gripper_open": [0]},
            "objects": [
                {"min_objects": 1, "max_objects": 1,
                 "location_pattern": "ATTACHED",
                 "type_pattern": held_type},
                scatter,
            ],
        }
    return {
        "robot": {"position": ["*"], "gripper_open": [1]},
        "objects": [scatter],
    }


def apply_initial_state(driver: SimDriver, config: SceneConfig,
                        state_def: Dict, seed: int) -> None:
    resolver = StateResolver()
    resolved = resolver.resolve(state_def=state_def, config=config,
                                current_state=None, initial_state=None,
                                random_seed=seed)
    driver.set_state(resolved)
