"""The model-side STATE (DSL §3) and the tool effects that mutate it (§3.1).

This object is the interpreter's running picture of the world — the same picture
the model is trained to keep. It is rendered verbatim into every ``STATE`` block
and is kept consistent with the simulator by applying the §3.1 effect of each
tool call as it is executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


UNKNOWN = "unknown"


@dataclass
class DslState:
    cursor: str = "step_1"
    position: str = UNKNOWN
    gripper: str = UNKNOWN          # open | closed | unknown
    held: str = UNKNOWN             # <ObjectType> | none | unknown
    scans: Dict[str, str] = field(default_factory=dict)   # location -> type (occupied only)
    visited: List[str] = field(default_factory=list)      # observe poses, this turn
    memory: Dict[str, object] = field(default_factory=dict)
    # last pick/place locations, for answer prose (not rendered in STATE)
    last_pick: Optional[str] = None
    last_place: Optional[str] = None

    def copy(self) -> "DslState":
        return DslState(
            cursor=self.cursor,
            position=self.position,
            gripper=self.gripper,
            held=self.held,
            scans=dict(self.scans),
            visited=list(self.visited),
            memory=dict(self.memory),
            last_pick=self.last_pick,
            last_place=self.last_place,
        )

    # --- turn / cursor bookkeeping ---

    def reset_turn(self) -> None:
        """visited and memory are turn-scoped (DSL §3); scans persist."""
        self.visited = []
        self.memory = {}

    # --- §3.1 tool effects ---

    def apply_move_to(self, position: str) -> None:
        self.position = position

    def apply_locate(self, position: str, covered_locations: List[str],
                      returned: Dict[str, str]) -> None:
        """append pose to visited; merge occupied slots; prune now-empty slots.

        ``covered_locations`` are the observe pose's observable locations in
        position-list (slot) order, which fixes a deterministic insertion order
        for ``scans`` (relevant to scene-wide ``first holding`` helpers).
        """
        if position not in self.visited:
            self.visited.append(position)
        for loc in covered_locations:
            if loc in returned:
                # re-insert in slot order: drop then set to refresh ordering
                self.scans.pop(loc, None)
                self.scans[loc] = returned[loc]
            else:
                self.scans.pop(loc, None)

    def apply_open_gripper(self) -> None:
        self.gripper = "open"
        self.held = "none"

    def apply_close_gripper(self, held_type: str = UNKNOWN) -> None:
        self.gripper = "closed"
        self.held = held_type

    def apply_get_gripper_state(self, value: str) -> None:
        self.gripper = value
        if value == "open":
            self.held = "none"

    def apply_get_position_state(self, value: str) -> None:
        self.position = value

    # --- pick/place bookkeeping (DSL §3.1 trailer) ---

    def after_pick(self, location: str) -> None:
        self.scans.pop(location, None)
        self.last_pick = location

    def after_place(self, location: str, obj_type: str) -> None:
        self.scans[location] = obj_type
        self.last_place = location
