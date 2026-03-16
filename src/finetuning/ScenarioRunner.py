"""Scenario runner for generating fine-tuning conversations via real MCP calls."""

import asyncio
import json
import random
from typing import Dict, List, Any, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pathlib import Path

from tool_simulation_server.scene import SceneConfig
from tool_simulation_server import config as sim_config
from finetuning.models import (
    ScenarioDraft, Conversation, ConversationMessage, ScenarioDraftsFile
)
from finetuning.variable_resolver import (
    VariableResolver, substitute_variables,
)
from finetuning.tool_routines import ToolRoutines, PICK_ROUTINES, PLACE_ROUTINES
from finetuning.prompts import SYSTEM_PROMPT


MCP_URL = "http://localhost:8000/mcp"
SIM_API_URL = "http://127.0.0.1:8001"
SCENES_DIR = sim_config.SCENES_DIR


def get_available_scenes() -> List[Path]:
    """Get list of available scene JSON files."""
    return list(SCENES_DIR.glob("*.json"))


def load_scene_config(scene_path: Path) -> SceneConfig:
    """Load a SceneConfig from a JSON file."""
    with open(scene_path) as f:
        data = json.load(f)
    return SceneConfig.from_dict(data)


class ScenarioRunner:
    """Runs scenario drafts against a simulation via MCP calls."""

    def __init__(
        self,
        scenario_drafts_path: str,
        system_prompt: str = SYSTEM_PROMPT
    ):
        with open(scenario_drafts_path) as f:
            data = json.load(f)
        drafts_file = ScenarioDraftsFile(**data)
        self.scenario_drafts = {d.id: d for d in drafts_file.scenarios}
        self.system_prompt = system_prompt
        self.scene_config: Optional[SceneConfig] = None

    async def load_scene(self, scene_name: str) -> None:
        """Load a scene into the simulation via SimServer API."""
        async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
            resp = await client.post("/scene/load", params={"name": scene_name})
            resp.raise_for_status()

            # Get scene config from API for variable resolution
            desc = await client.get("/scene/description")
            desc.raise_for_status()
            self.scene_config = SceneConfig.from_dict(desc.json()["config"])

    async def run_scenario(
        self,
        draft_id: str,
        scene_name: Optional[str] = None,
        random_seed: Optional[int] = None
    ) -> Conversation:
        """
        Run a single scenario and return a conversation.

        Args:
            draft_id: ID of the scenario draft to run
            scene_name: Optional scene name. If provided, loads this scene first.
            random_seed: Optional random seed for reproducibility

        Returns:
            Conversation object with the full message history.
        """
        # Load scene if name provided
        if scene_name is not None:
            await self.load_scene(scene_name)

        if self.scene_config is None:
            raise ValueError("No scene loaded. Call load_scene() first or provide scene_name.")

        draft = self.scenario_drafts[draft_id]

        # 1. Resolve variables
        resolver = VariableResolver(self.scene_config, random_seed)
        resolved_vars = resolver.resolve_all(draft.variables)

        # 2. Set initial state via SimServer
        await self._set_initial_state(draft, resolved_vars)

        # 3. Apply 3% gripper injection
        if draft.tool_routine in PICK_ROUTINES and random.random() < 0.03:
            await self._inject_gripper_holding()
        elif draft.tool_routine in PLACE_ROUTINES and random.random() < 0.03:
            await self._inject_gripper_open()

        # 4. Build initial messages (no system prompt - added during dataset formatting)
        messages: List[ConversationMessage] = [
            ConversationMessage(
                role="user",
                content=substitute_variables(random.choice(draft.prompt_templates), resolved_vars)
            )
        ]

        # 5. Execute tool routine via MCP
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                routines = ToolRoutines(session, self.scene_config, resolved_vars, draft)
                routine_method = getattr(routines, draft.tool_routine, None)

                if routine_method is None:
                    raise ValueError(f"Unknown tool routine: {draft.tool_routine}")

                outcome, tool_messages = await routine_method()
                messages.extend(tool_messages)

        # 5. Add final assistant message
        final_msg_template = draft.final_messages.get(outcome, f"Completed with outcome: {outcome}")
        final_msg = substitute_variables(final_msg_template, resolved_vars)
        messages.append(ConversationMessage(role="assistant", content=final_msg))

        # 6. Return conversation with metadata
        scene_id = scene_name
        return Conversation(
            messages=messages,
            metadata={
                "draft_id": draft_id,
                "scene_id": scene_id,
                "outcome": outcome
            }
        )

    async def _set_initial_state(
        self,
        draft: ScenarioDraft,
        resolved_vars: Dict[str, str]
    ) -> None:
        """Set the initial scene state via SimServer API."""
        state_dict = self._substitute_state_vars(
            draft.initial_state.model_dump(),
            resolved_vars
        )

        async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
            resp = await client.post("/scene/resolve_and_set_state", json=state_dict)
            resp.raise_for_status()

    async def _inject_gripper_holding(self) -> None:
        """3% injection: close gripper and attach a random object."""
        state = {
            "robot": {"position": ["prev"], "gripper_open": [0]},
            "objects": [
                {"min_objects": 1, "max_objects": 1,
                 "location_pattern": "ATTACHED", "type_pattern": "*"}
            ]
        }
        async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
            resp = await client.post("/scene/resolve_and_set_state", json=state)
            resp.raise_for_status()

    async def _inject_gripper_open(self) -> None:
        """3% injection: open gripper (not holding anything)."""
        state = {
            "robot": {"position": ["prev"], "gripper_open": [1]},
            "objects": "prev"
        }
        async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
            resp = await client.post("/scene/resolve_and_set_state", json=state)
            resp.raise_for_status()

    def _substitute_state_vars(
        self,
        state_dict: Dict[str, Any],
        resolved_vars: Dict[str, str]
    ) -> Dict[str, Any]:
        """Recursively substitute variables in state dict."""
        if isinstance(state_dict, dict):
            return {
                k: self._substitute_state_vars(v, resolved_vars)
                for k, v in state_dict.items()
            }
        elif isinstance(state_dict, list):
            return [self._substitute_state_vars(item, resolved_vars) for item in state_dict]
        elif isinstance(state_dict, str):
            # Substitute variable references
            for var_name, value in resolved_vars.items():
                state_dict = state_dict.replace(var_name, value)
            return state_dict
        else:
            return state_dict


async def run_scenario_demo():
    """Demo function to run a scenario."""
    # Get available scenes
    scenes = get_available_scenes()
    if not scenes:
        print("No scene files found in", SCENES_DIR)
        return

    print(f"Found {len(scenes)} scene files:")
    for s in scenes:
        print(f"  - {s.name}")

    # Use first scene
    scene_path = scenes[0]
    scene_name = scene_path.stem
    print(f"\nUsing scene: {scene_name}")

    # Create runner
    drafts_path = Path(__file__).parent / "scenario_drafts.json"
    runner = ScenarioRunner(str(drafts_path))

    # Run a scenario with the scene
    conversation = await runner.run_scenario("2.1", scene_name=scene_name)

    # Print conversation
    print(f"=== Generated Conversation ===")
    for msg in conversation.messages:
        print(f"\n[{msg.role}]")
        if msg.content:
            print(msg.content)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"Tool: {tc['function']['name']}({tc['function']['arguments']})")

    print(f"\n=== Conversation Metadata ===")
    print(json.dumps(conversation.metadata, indent=2))


if __name__ == "__main__":
    asyncio.run(run_scenario_demo())
