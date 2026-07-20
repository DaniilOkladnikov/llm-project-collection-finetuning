from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from env_sim_errors import *
import time
from functools import wraps
import threading
import queue
from scene import (
    Scene, SceneConfig, SceneState,
    Robot, Position, ObjectLocation, Object, PositionType, NamedSpot,
)


OK = 200


# --- 1. SHARED DATA STRUCTURES ---


@dataclass
class Command:
    method: str
    args: Dict[str, Any] = field(default_factory=dict)
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[Exception] = None


class SharedState:
    def __init__(self):
        self.scene: Optional[Scene] = None
        self.commands: "queue.Queue[Command]" = queue.Queue()
        self.last_scan_results: Optional[Dict[str, Dict[str, str]]] = None


# --- 2. THE SIMULATION SERVER ---


class Simulation:
    """Owns the SharedState and runs the main logic in a single thread."""

    def __init__(self, shared_state: SharedState):
        self.state = shared_state
        print("Simulation Server Initialized (no scene loaded).")

    def run_sim_loop(self):
        while True:
            cmd: Command = self.state.commands.get()
            print(f"Simulation executing: {cmd.method} {cmd.args}")

            try:
                handler = getattr(self, f"_cmd_{cmd.method}", None)
                if handler is None:
                    raise ValueError(f"Unknown command method: {cmd.method}")
                cmd.result = handler(**cmd.args)
            except Exception as e:
                cmd.error = e
                print(f"Simulation Error: {e}")
            finally:
                cmd.event.set()

            time.sleep(0.01)

    def _require_scene(self) -> Scene:
        if self.state.scene is None:
            raise RuntimeError("No scene loaded. Load a scene first via /scene/load.")
        return self.state.scene

    def update_viz(self):
        if self._viz:
            self._viz.request_draw()

    # --- Command Logic ---

    def _cmd_move_to(self, position: str) -> None:
        scene = self._require_scene()
        robot = scene.robot

        pos = scene.position_by_name(position)
        if pos is None:
            raise UnknownPositionError(f"Position '{position}' is not known.")
        robot.position = pos

        return None

       
    def _cmd_open_gripper(self) -> None:
        scene = self._require_scene()
        robot = scene.robot

        robot.gripper_open = True

        held_obj = scene.robot_held()
        if held_obj:
            target_loc = scene.undefined_location
            bound_loc = robot.position.bound_location
            bound_type = robot.position.bound_type
            if robot.position.is_place():
                occupant = scene.object_by_location(bound_loc)
                if not occupant and held_obj.type == bound_type:
                    target_loc = robot.position.bound_location or scene.undefined_location
            held_obj.location = target_loc

        return None

       
    def _cmd_close_gripper(self) -> None:
        scene = self._require_scene()
        robot = scene.robot

        if robot.gripper_open and scene.robot_held() is None and robot.position.is_pick():
            bound_loc = robot.position.bound_location
            bound_type = robot.position.bound_type
            if bound_loc is not None and bound_type is not None:
                occupant = scene.object_by_location(bound_loc)
                if occupant and occupant.type == bound_type and scene.is_position_observed(robot.position.name):
                    occupant.location = scene.attached_location
                    robot.gripper_open = False
                else:
                    raise CloseGripperError("Closing gripper failed: pick conditions not met")
            else:
                raise CloseGripperError("Closing gripper failed: position has no bound location/type")
        else:
            raise CloseGripperError("Closing gripper failed")

        return None

       
    def _cmd_locate_shapes(self) -> Dict[str, str]:
        scene = self._require_scene()
        robot = scene.robot

        results: Dict[str, str] = {}

        if robot.position.is_observe():
            observable_locs = robot.position.observable_locations or set()
            for loc in observable_locs:
                occupant = scene.object_by_location(loc)
                if occupant:
                    pick_pos = scene.pick_position_by_loc_and_type(location=loc, type=occupant.type)
                    if pick_pos:
                        scene.mark_position_observed(pick_pos.name)
                    results[loc.name] = f'{occupant.type}'

        self.state.last_scan_results = results
        return results

    def _cmd_get_scene_state(self) -> Dict[str, Any]:
        scene = self._require_scene()
        state = scene.get_state()
        return {
            "robot": {
                "position": state.robot_position,
                "gripper_open": state.robot_gripper_open,
            },
            "object_types": list(scene.config.object_types),
            "object_locations": list(scene.config.object_locations),
            "objects": {
                obj.id: {"id": obj.id, "type": obj.type, "location": obj.location.name}
                for obj in scene.objects.values()
            },
            "observed_positions": list(state.observed_positions),
        }

       
    def _cmd_set_scene_state(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        scene = self._require_scene()
        new_state = SceneState.from_dict(state_dict)
        scene.set_state(new_state)
        return {"status": "ok", "code": OK}

    def _cmd_get_scene_description(self) -> Dict[str, Any]:
        scene = self._require_scene()
        return {
            "config": scene.config.to_dict(),
            "state": scene.get_state().to_dict(),
            "initial_state": scene.initial_state.to_dict(),
        }

    def _cmd_reset_position_observance(self) -> Dict[str, Any]:
        scene = self._require_scene()
        scene.state.observed_positions.clear()
        return {"status": "ok", "code": OK}

    def _cmd_get_robot_position(self) -> str:
        scene = self._require_scene()
        return scene.robot.position.name

    def _cmd_get_gripper_state(self) -> str:
        scene = self._require_scene()
        return "open" if scene.robot.gripper_open else "closed"

    def _cmd_list_positions(self) -> list:
        scene = self._require_scene()
        return list(scene.config.positions.keys())

       
    def _cmd_load_scene(self, scene_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Load a new scene from JSON with config + initial_state structure."""
        config_data = scene_dict.get("config", scene_dict)
        initial_state_data = scene_dict.get("initial_state")

        config = SceneConfig.from_dict(config_data)

        if initial_state_data:
            initial_state = SceneState.from_dict(initial_state_data)
        else:
            robot_start = config_data.get("robot_start")
            if isinstance(robot_start, dict):
                robot_start = robot_start.get("position")
            start_pos = (
                robot_start
                if robot_start and robot_start in config.positions
                else list(config.positions.keys())[0]
            )
            initial_state = SceneState(
                robot_position=start_pos,
                robot_gripper_open=True,
                object_locations={
                    int(obj_id): "UNDEFINED"
                    for obj_id in config.objects.keys()
                },
                observed_positions=set(),
            )

        self.state.scene = Scene(
            config=config,
            state=initial_state.copy(),
            initial_state=initial_state,
        )
        self.state.last_scan_results = None

        return {"status": "ok", "code": OK}
