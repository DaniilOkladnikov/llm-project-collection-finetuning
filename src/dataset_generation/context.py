"""Scene view, role binding, and the evaluation context.

* :class:`SceneView` precomputes everything the helpers need from a
  ``SceneConfig`` (slot order, observe coverage, pick/place pose lookup).
* :class:`Role` / :class:`Binding` hold the per-scenario resolution of the task
  variables (X/W object types, A/B targets) — DSL step (1).
* :class:`EvalContext` bundles the running :class:`DslState`, the binding, and
  the scene view; it is threaded through every helper/condition evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from tool_simulation_server.scene import SceneConfig

from dataset_generation.dsl_state import DslState


class SceneView:
    """Read-only, precomputed view over a scene's topology."""

    def __init__(self, config: SceneConfig):
        self.config = config

        self.object_locations: List[str] = [
            loc for loc in config.object_locations
            if loc not in ("ATTACHED", "UNDEFINED")
        ]
        self.slot_index: Dict[str, int] = {
            loc: i for i, loc in enumerate(self.object_locations)
        }

        # observe poses, in position-list order, with their covered locations
        self.observe_poses: List[str] = []
        self.observe_coverage: Dict[str, List[str]] = {}
        self._pick: Dict[tuple, str] = {}
        self._place: Dict[tuple, str] = {}
        for name, pos in config.positions.items():
            if pos.type == "OBSERVE" and pos.observable_locations:
                self.observe_poses.append(name)
                self.observe_coverage[name] = list(pos.observable_locations)
            elif pos.type == "PICK":
                self._pick[(pos.bound_type, pos.bound_location)] = name
            elif pos.type == "PLACE":
                self._place[(pos.bound_type, pos.bound_location)] = name

        # location -> observe poses that cover it (position-list order)
        self.covering_poses: Dict[str, List[str]] = {}
        for pose in self.observe_poses:
            for loc in self.observe_coverage[pose]:
                self.covering_poses.setdefault(loc, []).append(pose)

        # validated collections: only those whose members are all real locations
        self.collections: Dict[str, List[str]] = {}
        if config.location_names:
            valid = set(self.object_locations)
            for name, members in config.location_names.items():
                if members and all(m in valid for m in members):
                    self.collections[name] = list(members)

    # --- lookups ---

    def pick_pose(self, obj_type: str, location: str) -> Optional[str]:
        return self._pick.get((obj_type, location))

    def place_pose(self, obj_type: str, location: str) -> Optional[str]:
        return self._place.get((obj_type, location))

    def observe_pose_for(self, location: str) -> Optional[str]:
        poses = self.covering_poses.get(location)
        return poses[0] if poses else None

    def in_slot_order(self, locations: List[str]) -> List[str]:
        return sorted(locations, key=lambda l: self.slot_index.get(l, 1 << 30))

    def expand(self, name: str) -> List[str]:
        """Expand a target name to its member locations (slot order)."""
        if name in self.collections:
            return self.in_slot_order(self.collections[name])
        if name in self.slot_index:
            return [name]
        return []


@dataclass
class Role:
    """A resolved task variable.

    For object types (X/W): ``phrase`` and ``value`` are the type name,
    ``locations`` is empty. For targets (A/B): ``phrase`` is the name as it
    appears in the prompt, ``locations`` is its members in slot order, and
    ``is_collection`` flags group targets.
    """
    name: str                       # role token: "X", "W", "A", "B"
    phrase: str                     # text used in MAP/PROGRAM
    is_target: bool
    value: Optional[str] = None     # type name (for X/W)
    locations: List[str] = field(default_factory=list)
    is_collection: bool = False


class Binding:
    def __init__(self, roles: Dict[str, Role]):
        self.roles = roles

    def __contains__(self, name: str) -> bool:
        return name in self.roles

    def get(self, name: str) -> Role:
        return self.roles[name]

    def phrase(self, name: str) -> str:
        return self.roles[name].phrase

    def type_value(self, name: str) -> str:
        return self.roles[name].value

    def locations(self, name: str) -> List[str]:
        return self.roles[name].locations


@dataclass
class EvalContext:
    state: DslState
    binding: Binding
    view: SceneView
    # step-scoped temporary variables (DSL §5.5.6); reset per step by the interpreter
    temps: Dict[str, object] = field(default_factory=dict)
    # the simulator's ground truth at the start of the current step, used to
    # resolve `check position` / `check gripper` driven remembers deterministically
    sim_truth: Dict[str, str] = field(default_factory=dict)
