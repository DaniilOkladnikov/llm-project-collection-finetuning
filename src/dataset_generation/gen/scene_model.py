"""A self-contained, mutable scene model built from a generated scene dict.

The DSL model only ever observes the world through two channels:

* ``list_avaliable_robot_positions`` -> the position-name list, and
* ``locate_shapes`` at an observe pose -> ``{loc: type}`` for occupied slots.

So the object-instance list in the scene config is invisible to the model; the
only thing that matters is *occupancy* (which location holds which type) and the
*positions* (which encode every pick/place/observe the robot can do). This class
mirrors ``simulation.py``'s observable behaviour: it resolves positions by
structural match (type / bound_location / observable_locations) exactly as
required, and ``locate`` returns only occupied observable slots.

Occupancy is free to set for back-solving, subject to one rule that keeps a
state physically realisable: a location may only hold a type that has a pick
position there (otherwise the robot could never have placed / could never pick
it).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


PICK, PLACE, OBSERVE, GENERAL = "PICK", "PLACE", "OBSERVE", "GENERAL"


class SceneModel:
    def __init__(self, scene: dict):
        self.scene = scene
        self.positions: Dict[str, dict] = dict(scene["positions"])
        self.position_names: List[str] = list(self.positions.keys())
        self.object_types: List[str] = list(scene["object_types"])
        self.object_locations: List[str] = list(scene["object_locations"])
        self.location_names: Dict[str, List[str]] = dict(scene.get("location_names") or {})

        # index positions by role
        self._pick: Dict[Tuple[str, str], str] = {}
        self._place: Dict[Tuple[str, str], str] = {}
        self._observe: List[Tuple[str, List[str]]] = []
        self._general: List[str] = []
        for name, cfg in self.positions.items():
            t = cfg["type"]
            if t == PICK:
                self._pick[(cfg["bound_type"], cfg["bound_location"])] = name
            elif t == PLACE:
                self._place[(cfg["bound_type"], cfg["bound_location"])] = name
            elif t == OBSERVE:
                self._observe.append((name, list(cfg.get("observable_locations") or [])))
            elif t == GENERAL:
                self._general.append(name)

        # canonical location order = first appearance across observe poses
        order: List[str] = []
        seen = set()
        for _name, locs in self._observe:
            for loc in locs:
                if loc not in seen:
                    seen.add(loc)
                    order.append(loc)
        # any location never covered by an observe pose is appended last
        for loc in self.object_locations:
            if loc not in seen:
                seen.add(loc)
                order.append(loc)
        self.canonical_order: List[str] = order
        self._order_index = {loc: i for i, loc in enumerate(order)}

        # types that can be picked somewhere / placed somewhere
        self.pickable_types = sorted({t for (t, _l) in self._pick})

        # --- mutable state -------------------------------------------------
        self.occupancy: Dict[str, Optional[str]] = {loc: None for loc in self.canonical_order}
        self.gripper_open: bool = True
        self.held: Optional[str] = None      # type held, or None
        self.robot_position: str = self.home() or (self.position_names[0] if self.position_names else "home")

    # --- structural position lookups ---------------------------------------

    def pick_pos(self, obj_type: str, loc: str) -> Optional[str]:
        return self._pick.get((obj_type, loc))

    def place_pos(self, obj_type: str, loc: str) -> Optional[str]:
        return self._place.get((obj_type, loc))

    def observe_positions(self) -> List[Tuple[str, List[str]]]:
        return list(self._observe)

    def observe_pos_for_loc(self, loc: str) -> Optional[str]:
        for name, locs in self._observe:
            if loc in locs:
                return name
        return None

    def home(self) -> Optional[str]:
        for g in self._general:
            if g == "home":
                return "home"
        return self._general[0] if self._general else None

    # --- location collections ---------------------------------------------

    def placeable_types_at(self, loc: str) -> List[str]:
        return sorted({t for (t, l) in self._pick if l == loc})

    def locs_of_collection(self, name: str) -> Optional[List[str]]:
        if name in self.location_names:
            return self.order(self.location_names[name])
        if name in self.object_locations:
            return [name]
        return None

    def order(self, locs) -> List[str]:
        return sorted(locs, key=lambda l: self._order_index.get(l, 10**9))

    # --- observe cover -----------------------------------------------------

    def cover_for(self, target_locs: List[str], explored: List[str]) -> List[str]:
        """Smallest list of observe poses (not already explored) whose union
        covers ``target_locs``. Ties broken by config order."""
        from itertools import combinations
        target = set(target_locs)
        already = set()
        for p in explored:
            for name, locs in self._observe:
                if name == p:
                    already |= set(locs)
        need = target - already
        if not need:
            return []
        candidates = [(n, set(l)) for n, l in self._observe if n not in explored and (set(l) & need)]
        for size in range(1, len(candidates) + 1):
            best = None
            for combo in combinations(candidates, size):
                union = set().union(*(l for _n, l in combo))
                if need <= union:
                    best = [n for n, _l in combo]
                    break
            if best is not None:
                return best
        return [n for n, _l in candidates]  # fallback: everything relevant

    def revealed_locs(self, pose_names: List[str]) -> List[str]:
        """All observable locations across the given observe poses (canonical
        order)."""
        locs: List[str] = []
        seen = set()
        for name, plocs in self._observe:
            if name in pose_names:
                for loc in plocs:
                    if loc not in seen:
                        seen.add(loc)
                        locs.append(loc)
        return self.order(locs)

    def all_observe_cover(self, explored: List[str]) -> List[str]:
        """Cover for *everything* (all locations), excluding explored poses."""
        return self.cover_for(self.canonical_order, explored)

    # --- occupancy / truth -------------------------------------------------

    def set_occupancy(self, mapping: Dict[str, Optional[str]]) -> None:
        for loc in self.canonical_order:
            self.occupancy[loc] = mapping.get(loc)

    def truth_snapshot(self) -> dict:
        return {
            "occupancy": dict(self.occupancy),
            "gripper_open": self.gripper_open,
            "held": self.held,
            "robot_position": self.robot_position,
        }

    def restore(self, snap: dict) -> None:
        self.occupancy = dict(snap["occupancy"])
        self.gripper_open = snap["gripper_open"]
        self.held = snap["held"]
        self.robot_position = snap["robot_position"]

    def locate_at(self, pose_name: str) -> Dict[str, str]:
        """Ground-truth locate result at an observe pose: occupied slots only,
        in canonical order."""
        for name, locs in self._observe:
            if name == pose_name:
                out = {}
                for loc in self.order(locs):
                    occ = self.occupancy.get(loc)
                    if occ:
                        out[loc] = occ
                return out
        return {}
