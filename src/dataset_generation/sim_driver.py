"""Headless simulator + the DSL tool-surface adapter.

The DSL (``DSL.md``) speaks a specific tool vocabulary
(``get_positions``, ``get_gripper_state``, ``get_position_state``, ``move_to``,
``open_gripper``, ``close_gripper``, ``locate_shapes``) and expects every tool to
return the uniform ``{"status", "content"}`` envelope.

The installed ``tool_simulation_server.simulation.Simulation`` exposes a slightly
different ``_cmd_*`` surface and, in ``__init__``, spins up an SVG viewer. We:

* subclass it as :class:`HeadlessSim` to skip the viewer and the command thread,
  calling the ``_cmd_*`` methods directly and synchronously, and
* wrap it in :class:`SimDriver`, the single place that bridges the DSL tool names
  to ``_cmd_*`` and formats the envelope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from tool_simulation_server.simulation import Simulation, SharedState
from tool_simulation_server.scene import SceneState


class HeadlessSim(Simulation):
    """A :class:`Simulation` with no visualization and no background thread.

    The base ``__init__`` constructs an ``EnvSimSVG`` viewer (auto-opening a
    browser) and is meant to be driven through a command queue on a worker
    thread. For batch dataset generation we want neither, so we bypass
    ``__init__`` entirely and call the ``_cmd_*`` handlers directly.
    """

    def __init__(self) -> None:  # noqa: D107 - see class docstring
        self.state = SharedState()
        self._viz = None


class ToolError(Exception):
    """Raised internally; callers use the envelope instead."""


class SimDriver:
    """Exposes the 7-tool DSL surface over a :class:`HeadlessSim`.

    Every public tool method returns ``{"status": "OK"|"ERROR", "content": ...}``.
    ``content`` is ``None`` for actuation tools (move/open/close), a primitive for
    the getters, and a ``{location: type}`` dict for ``locate_shapes``.
    """

    def __init__(self) -> None:
        self.sim = HeadlessSim()

    # --- scene / state management (not part of the model-visible tool surface) ---

    def load_scene_dict(self, scene_dict: Dict[str, Any]) -> None:
        self.sim._cmd_load_scene(scene_dict=scene_dict)

    def load_scene_file(self, path: Path) -> Dict[str, Any]:
        with open(path) as f:
            scene_dict = json.load(f)
        self.load_scene_dict(scene_dict)
        return scene_dict

    def set_state(self, state: SceneState) -> None:
        self.sim._cmd_set_scene_state(state_dict=state.to_dict())

    def get_scene_state(self) -> Dict[str, Any]:
        return self.sim._cmd_get_scene_state()

    def get_scene_description(self) -> Dict[str, Any]:
        return self.sim._cmd_get_scene_description()

    # --- the DSL tool surface (each returns the {status, content} envelope) ---

    def get_positions(self) -> Dict[str, Any]:
        return self._ok(self.sim._cmd_get_positions())

    def get_gripper_state(self) -> Dict[str, Any]:
        # Normalize to "open"/"closed" only; never leak the held object type
        # (matches DSL §3.1 and the robot-tool-envelope contract).
        status = self.sim._cmd_get_robot_status()
        gripper = "open" if status["gripper_state"] == "open" else "closed"
        return self._ok(gripper)

    def get_position_state(self) -> Dict[str, Any]:
        status = self.sim._cmd_get_robot_status()
        return self._ok(status["position"]["name"])

    def move_to(self, position: str) -> Dict[str, Any]:
        return self._actuate(lambda: self.sim._cmd_move_to(position=position))

    def open_gripper(self) -> Dict[str, Any]:
        return self._actuate(lambda: self.sim._cmd_open_gripper())

    def close_gripper(self) -> Dict[str, Any]:
        # _cmd_close_gripper requires a (functionally unused) mode argument.
        return self._actuate(lambda: self.sim._cmd_close_gripper(mode="default"))

    def locate_shapes(self) -> Dict[str, Any]:
        return self._ok(self.sim._cmd_locate_objects())

    # --- dispatch by DSL tool name (used by the interpreter) ---

    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = args or {}
        method = getattr(self, name, None)
        if method is None or name.startswith("_") or name not in _TOOL_NAMES:
            return {"status": "ERROR", "content": f"unknown tool: {name}"}
        try:
            return method(**args)
        except Exception as e:  # pragma: no cover - defensive
            return {"status": "ERROR", "content": str(e)}

    # --- helpers ---

    @staticmethod
    def _ok(content: Any) -> Dict[str, Any]:
        return {"status": "OK", "content": content}

    @staticmethod
    def _actuate(fn) -> Dict[str, Any]:
        try:
            fn()
            return {"status": "OK", "content": None}
        except Exception as e:
            return {"status": "ERROR", "content": str(e)}


_TOOL_NAMES = {
    "get_positions",
    "get_gripper_state",
    "get_position_state",
    "move_to",
    "open_gripper",
    "close_gripper",
    "locate_shapes",
}
