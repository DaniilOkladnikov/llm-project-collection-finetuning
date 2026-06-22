"""Run one (task, scene, seed) scenario into a list of dataset entries."""

from __future__ import annotations

import random
from pathlib import Path
from typing import List

from tool_simulation_server.scene import SceneConfig

from dataset_generation.context import SceneView
from dataset_generation.interpreter import Entry, Interpreter
from dataset_generation.resolve import (
    apply_initial_state, build_binding, build_initial_dsl_state,
    check_compatibility, held_type_for, make_state_def, scene_capabilities,
)
from dataset_generation.sim_driver import SimDriver
from dataset_generation.taskspec import TaskSpec


def run_scenario(task: TaskSpec, scene_path: Path, seed: int) -> List[Entry]:
    driver = SimDriver()
    scene_dict = driver.load_scene_file(scene_path)
    config = SceneConfig.from_dict(scene_dict.get("config", scene_dict))
    view = SceneView(config)

    caps = scene_capabilities(view)
    binding = build_binding(task, config, view, seed)
    check_compatibility(task, binding, view, caps)

    held_type = held_type_for(task, binding, random.Random(seed + 2))
    state_def = make_state_def(held_type, view, list(config.object_types))
    apply_initial_state(driver, config, state_def, seed + 1)

    dsl_state = build_initial_dsl_state(held_type)

    def phrase(name: str):
        return binding.roles[name].phrase if name in binding else None

    metadata = {
        "task_id": task.id,
        "scene": scene_path.stem,
        "intent": task.intent,
        "seed": seed,
        "X": phrase("X"), "W": phrase("W"), "A": phrase("A"), "B": phrase("B"),
    }

    return Interpreter(task, task.program, binding, view, driver, dsl_state, metadata).run()
