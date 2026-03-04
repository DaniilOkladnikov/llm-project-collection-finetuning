"""Tool routines for generating fine-tuning conversations via MCP calls."""

import json
import random
from typing import Dict, List, Any, Tuple

from mcp import ClientSession, types

from tool_simulation_server.scene import SceneConfig
from finetuning.models import ScenarioDraft, ConversationMessage
from finetuning.variable_resolver import (
    expand_location, find_observe_positions_for_locations,
    find_pick_position, find_place_position, get_all_observe_positions,
    is_location_group, get_sample_positions_for_locations,
)
from finetuning.variable_resolver import substitute_variables
from finetuning.prompts import (
    # shared helpers
    decouple_location_group,
    decouple_simple_location,
    observe_locations_first_move,
    observe_locations_subsequent_move,
    observe_locations_scan,
    execute_pick_move,
    execute_pick_close,
    execute_place_move,
    execute_place_open,
    early_stop_found_empty,
    # observe_and_pick
    observe_and_pick_init,
    observe_and_pick_gripper_ready,
    observe_and_pick_first_move,
    observe_and_pick_subsequent_move,
    observe_and_pick_scan,
    observe_and_pick_move_to_pick,
    observe_and_pick_close_gripper,
    # search_all_and_pick
    search_all_and_pick_init,
    search_all_and_pick_gripper_ready,
    search_all_and_pick_first_move,
    search_all_and_pick_subsequent_move,
    search_all_and_pick_scan,
    search_all_and_pick_move_to_pick,
    search_all_and_pick_close_gripper,
    # observe_and_place
    observe_and_place_init,
    observe_and_place_gripper_ready,
    observe_and_place_first_move,
    observe_and_place_subsequent_move,
    observe_and_place_scan,
    observe_and_place_decide,
    observe_and_place_open_gripper,
    # status_only
    status_only_check,
    # navigate_to
    navigate_to_check_position,
    navigate_to_load_positions,
    navigate_to_pick_position,
    navigate_to_merged_first_obs,
    navigate_to_merged_subsequent_obs,
    navigate_to_observe_first,
    navigate_to_observe_subsequent,
    navigate_to_home,
    # observe_and_report
    observe_and_report_check_status,
    observe_and_report_load_positions,
    # observe_and_report_all
    observe_and_report_all_check_status,
    observe_and_report_all_load_positions,
    observe_and_report_all_plan,
    # observe_and_pick_any
    observe_and_pick_any_check_gripper,
    observe_and_pick_any_load_positions,
    # observe_and_pick_return_origin
    pick_return_origin_check_status,
    pick_return_origin_load_positions,
    pick_return_origin_return_success,
    pick_return_origin_return_empty,
    pick_return_origin_return_wrong_type,
    pick_return_origin_return_any_success,
    pick_return_origin_return_any_empty,
    # search_all_and_place
    search_all_and_place_check_gripper,
    search_all_and_place_load_positions,
    search_all_place_context_generic,
    search_all_place_context_prefer,
    search_all_place_context_avoid,
    search_all_and_place_first_scan,
    search_all_and_place_subsequent_scan,
    search_all_and_place_locate,
    # observe_and_place_with_fallback
    place_with_fallback_check_gripper,
    place_with_fallback_load_positions,
    place_fallback_context_yz,
    place_fallback_context_strict,
    place_fallback_context_conditional,
    place_fallback_non_w_found,
    place_fallback_y_empty_no_w,
    # pick_and_place
    pick_and_place_check_gripper,
    pick_and_place_load_positions,
    pick_and_place_context,
    pick_and_place_transition,
    pick_and_place_return_to_source,
    pick_and_place_return_open_gripper,
    # pick scenario context
    observe_and_pick_context,
    search_all_and_pick_context,
    observe_and_pick_any_context_xw,
    observe_and_pick_any_context_unless_w,
    observe_and_pick_any_context_y_else_z,
    observe_and_pick_any_context_whatever,
    pick_return_origin_context,
    # observe_conditional_pick
    observe_conditional_pick_init,
    observe_conditional_pick_gripper_ready,
    observe_conditional_pick_context,
    observe_conditional_pick_found_x,
    observe_conditional_pick_found_different,
    observe_conditional_pick_found_empty,
    # compare_inventories
    compare_inventories_check_status,
    compare_inventories_load_positions,
    compare_inventories_plan,
    compare_inventories_summary,
    # place_implicit_type
    place_implicit_type_init,
    place_implicit_type_gripper_ready,
    place_implicit_type_context,
    place_implicit_type_decide,
)


PICK_ROUTINES = {
    "observe_and_pick", "observe_and_pick_any",
    "observe_and_pick_return_origin", "search_all_and_pick",
    "pick_and_place", "observe_conditional_pick",
}
PLACE_ROUTINES = {
    "observe_and_place", "search_all_and_place",
    "observe_and_place_with_fallback", "place_implicit_type",
}


class ToolRoutines:
    """Tool routines with explicit Chain-of-Thought reasoning injection."""

    def __init__(
        self,
        session: ClientSession,
        scene_config: SceneConfig,
        resolved_vars: Dict[str, str],
        draft: ScenarioDraft = None
    ):
        self.session = session
        self.config = scene_config
        self.vars = resolved_vars
        self.draft = draft

    async def _call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any] = None
    ) -> Any:
        """Call an MCP tool and return the result."""
        arguments = arguments or {}
        result = await self.session.call_tool(tool_name, arguments)

        # Extract content from result - collect all text content items
        if hasattr(result, 'content') and result.content:
            text_items = []
            for c in result.content:
                if isinstance(c, types.TextContent):
                    text_items.append(c.text)

            if len(text_items) == 1:
                # Single content item - try to parse as JSON
                try:
                    return json.loads(text_items[0])
                except json.JSONDecodeError:
                    return text_items[0]
            elif len(text_items) > 1:
                # Multiple content items - try to parse each as JSON
                parsed_items = []
                for text in text_items:
                    try:
                        parsed_items.append(json.loads(text))
                    except json.JSONDecodeError:
                        parsed_items.append(text)
                return parsed_items
        return None

    async def _call_and_record(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        messages: List[ConversationMessage],
        reasoning: str = ""
    ) -> Any:
        """
        Call a tool and record the call/response in messages with explicit reasoning.
        """
        # 1. Record assistant thought + tool call
        messages.append(ConversationMessage(
            role="assistant",
            content=reasoning,  # <--- INJECT REASONING HERE
            tool_calls=[{
                "function": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }]
        ))

        # 2. Execute and record result
        result = await self._call_tool(tool_name, arguments)

        # 3. Format result for tool message
        if isinstance(result, (dict, list, tuple)):
            content = json.dumps(result)
        else:
            content = str(result) if result is not None else "OK"

        messages.append(ConversationMessage(
            role="tool",
            content=content
        ))

        return result

    # ─── helpers ───────────────────────────────────────────────────────

    def _extract_gripper(self, status: Any) -> str:
        """Return gripper state string: 'open' or the held object type."""
        if isinstance(status, dict):
            return status.get("gripper_state", "unknown")
        if isinstance(status, (list, tuple)):
            return str(status[0])
        return str(status)

    def _extract_position(self, status: Any) -> str:
        """Return current position name from a get_status result."""
        if isinstance(status, dict):
            pos = status.get("position", {})
            if isinstance(pos, dict):
                return pos.get("name", "unknown")
            return str(pos)
        return "unknown"

    def _decoupling_prefix(self, var_name: str) -> str:
        """Return decoupling reasoning for location groups or simple locations."""
        location_value = self.vars.get(var_name, "")
        if not location_value:
            return ""
        if is_location_group(location_value, self.config):
            expanded = expand_location(location_value, self.config)
            samples = get_sample_positions_for_locations(expanded, self.config)
            return decouple_location_group(location_value, expanded, samples) + " "
        # Simple object location: confirm from positions list
        samples = get_sample_positions_for_locations([location_value], self.config)
        if samples:
            return decouple_simple_location(location_value, samples) + " "
        return ""

    def _resolved_prompt(self) -> str:
        """Reconstruct the resolved user prompt from draft template."""
        if self.draft and self.draft.prompt_templates:
            template = random.choice(self.draft.prompt_templates)
            return substitute_variables(template, self.vars)
        return ""

    def _get_visible_locations(
        self, obs_pos: str, target_locations: List[str] = None
    ) -> List[str]:
        """Get visible locations from an observe position, optionally filtered."""
        obs_cfg = self.config.positions.get(obs_pos)
        if not obs_cfg or not obs_cfg.observable_locations:
            return []
        if target_locations:
            return [loc for loc in obs_cfg.observable_locations if loc in target_locations]
        return list(obs_cfg.observable_locations)

    def _compute_remaining(
        self, target_locations: List[str], inspected: List[str]
    ) -> List[str]:
        """Compute which target locations haven't been covered by inspected positions."""
        checked = set()
        for prev_pos in inspected:
            prev_cfg = self.config.positions.get(prev_pos)
            if prev_cfg and prev_cfg.observable_locations:
                checked.update(
                    loc for loc in prev_cfg.observable_locations
                    if loc in target_locations
                )
        return [loc for loc in target_locations if loc not in checked]

    async def _observe_locations(
        self,
        target_locations: List[str],
        messages: List[ConversationMessage],
        purpose: str = "",
        early_stop_types: List[str] = None,
        suppress_nontarget_findings: bool = False,
    ) -> Dict[str, str]:
        """Navigate to observe positions, scan, return {loc: type} for targets."""
        obs_positions = find_observe_positions_for_locations(
            target_locations, self.config
        )
        findings: Dict[str, str] = {}
        inspected: List[str] = []

        for i, obs_pos in enumerate(obs_positions):
            visible_locs = self._get_visible_locations(obs_pos, target_locations)

            if i == 0:
                reasoning = observe_locations_first_move(
                    target_locations, obs_positions, obs_pos, purpose
                )
            else:
                remaining = self._compute_remaining(target_locations, inspected)
                reasoning = observe_locations_subsequent_move(
                    inspected, obs_pos, findings, remaining,
                    suppress_nontarget_findings=suppress_nontarget_findings,
                )

            await self._call_and_record(
                "move_to", {"pos": obs_pos}, messages, reasoning
            )

            reasoning = observe_locations_scan(obs_pos, visible_locs)
            shapes = await self._call_and_record(
                "locate_shapes", {}, messages, reasoning
            )
            inspected.append(obs_pos)

            if isinstance(shapes, dict):
                for loc, obj in shapes.items():
                    if loc in target_locations:
                        findings[loc] = obj

            # Early stop: target type found
            if early_stop_types and findings:
                if any(obj in early_stop_types for obj in findings.values()):
                    break

        return findings

    async def _execute_pick(
        self,
        obj_type: str,
        location: str,
        messages: List[ConversationMessage],
    ) -> bool:
        """Navigate to pick position and close gripper."""
        pick_pos = find_pick_position(obj_type, location, self.config)
        if not pick_pos:
            return False

        reasoning = execute_pick_move(obj_type, location, pick_pos)
        await self._call_and_record(
            "move_to", {"pos": pick_pos}, messages, reasoning
        )

        reasoning = execute_pick_close(pick_pos)
        await self._call_and_record("close_gripper", {}, messages, reasoning)
        return True

    async def _execute_place(
        self,
        obj_type: str,
        location: str,
        messages: List[ConversationMessage],
    ) -> bool:
        """Navigate to place position and open gripper."""
        place_pos = find_place_position(obj_type, location, self.config)
        if not place_pos:
            return False

        reasoning = execute_place_move(location, place_pos)
        await self._call_and_record(
            "move_to", {"pos": place_pos}, messages, reasoning
        )

        reasoning = execute_place_open()
        await self._call_and_record("open_gripper", {}, messages, reasoning)
        return True

    # ─── existing routines ───────────────────────────────────────────

    async def observe_and_pick(self) -> Tuple[str, List[ConversationMessage]]:
        """
        Pick $X from $Y.
        """
        messages: List[ConversationMessage] = []
        obj_type = self.vars.get("$X", "")
        location = self.vars.get("$Y", "")

        # 1. Initialization
        reasoning = observe_and_pick_init(obj_type, location)
        status = await self._call_and_record("get_status", {}, messages, reasoning)

        # Gripper Check
        gripper_state = status.get("gripper_state") if isinstance(status, dict) else (status[0] if isinstance(status, (list, tuple)) else status)
        if gripper_state != "open":
            return ("ask_user", messages)

        # 2. Get positions (The source of truth for the model)
        reasoning = observe_and_pick_gripper_ready()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Strategy Planning
        decoupling = self._decoupling_prefix("$Y")
        context = observe_and_pick_context(obj_type, location)
        object_locations = expand_location(location, self.config)
        observe_positions = find_observe_positions_for_locations(object_locations, self.config)

        # Track history
        inspected_positions = []
        all_findings: Dict[str, str] = {}

        # 4. Search Loop
        found_location = None
        for i, obs_pos in enumerate(observe_positions):
            visible_locs = self._get_visible_locations(obs_pos, object_locations)

            full_reasoning = ""

            if i == 0:
                # FIRST TURN: CONTEXT + PARSING & PLANNING
                full_reasoning = context + " " + decoupling + observe_and_pick_first_move(
                    location, obj_type, object_locations, observe_positions, obs_pos
                )
            else:
                # SUBSEQUENT TURNS: PROGRESS UPDATE
                remaining = self._compute_remaining(object_locations, inspected_positions)
                full_reasoning = observe_and_pick_subsequent_move(
                    inspected_positions, obj_type, obs_pos, remaining
                )

            # Move
            await self._call_and_record("move_to", {"pos": obs_pos}, messages, full_reasoning)

            # Locate
            reasoning = observe_and_pick_scan(obs_pos, obj_type, visible_locs)
            shapes = await self._call_and_record("locate_shapes", {}, messages, reasoning)

            # Record visit
            inspected_positions.append(obs_pos)

            # Track ALL findings for memory, check for target
            if isinstance(shapes, dict):
                for loc, obj in shapes.items():
                    if loc in object_locations:
                        all_findings[loc] = obj
                        if obj == obj_type and not found_location:
                            found_location = loc

            if found_location:
                break

        # 5. Outcome Handling
        if not found_location:
            return ("not_found", messages)

        self.vars["$FOUND_LOCATION"] = found_location

        # 6. Pick Execution
        pick_pos = find_pick_position(obj_type, found_location, self.config)

        if pick_pos:
            reasoning = observe_and_pick_move_to_pick(obj_type, found_location, pick_pos)
            await self._call_and_record("move_to", {"pos": pick_pos}, messages, reasoning)

            reasoning = observe_and_pick_close_gripper(pick_pos)
            await self._call_and_record("close_gripper", {}, messages, reasoning)

        return ("success", messages)


    async def search_all_and_pick(self) -> Tuple[str, List[ConversationMessage]]:
        """
        Find and pick $X (unknown location).
        """
        messages: List[ConversationMessage] = []
        obj_type = self.vars.get("$X", "")

        # 1. Initialization
        reasoning = search_all_and_pick_init(obj_type)
        status = await self._call_and_record("get_status", {}, messages, reasoning)

        # 1.1. Gripper Check
        gripper_state = status.get("gripper_state") if isinstance(status, dict) else (status[0] if isinstance(status, (list, tuple)) else status)
        if gripper_state != "open":
            return ("ask_user", messages)

        # 1.2 Get positions
        reasoning = search_all_and_pick_gripper_ready()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Strategy Planning (Parsing Simulation)
        context = search_all_and_pick_context(obj_type)
        all_observe = get_all_observe_positions(self.config)

        # Track history
        inspected_positions = []
        all_findings: Dict[str, str] = {}

        # 4. Global Search Loop
        found_location = None
        for i, obs_pos in enumerate(all_observe):
            visible_locs = self._get_visible_locations(obs_pos)

            if i == 0:
                full_reasoning = context + " " + search_all_and_pick_first_move(
                    all_observe, obj_type, obs_pos
                )
            else:
                full_reasoning = search_all_and_pick_subsequent_move(
                    inspected_positions, obs_pos
                )

            # Move
            await self._call_and_record("move_to", {"pos": obs_pos}, messages, full_reasoning)

            # Locate
            reasoning = search_all_and_pick_scan(obs_pos, obj_type, visible_locs)
            shapes = await self._call_and_record("locate_shapes", {}, messages, reasoning)

            # Record visit
            inspected_positions.append(obs_pos)

            # Track ALL findings, check for target
            if isinstance(shapes, dict):
                for loc, obj in shapes.items():
                    all_findings[loc] = obj
                    if obj == obj_type and not found_location:
                        found_location = loc

            if found_location:
                break

        # 5. Outcome
        if not found_location:
            return ("not_found", messages)

        self.vars["$FOUND_LOCATION"] = found_location

        # 6. Pick
        pick_pos = find_pick_position(obj_type, found_location, self.config)
        if pick_pos:
            reasoning = search_all_and_pick_move_to_pick(obj_type, found_location, pick_pos)
            await self._call_and_record("move_to", {"pos": pick_pos}, messages, reasoning)

            reasoning = search_all_and_pick_close_gripper(pick_pos)
            await self._call_and_record("close_gripper", {}, messages, reasoning)

        return ("success", messages)


    async def observe_and_place(self) -> Tuple[str, List[ConversationMessage]]:
        """
        Place $X into $Y.
        """
        messages: List[ConversationMessage] = []
        obj_type = self.vars.get("$X", "")
        location_group_name = self.vars.get("$Y", "")

        # 1. Initialization
        reasoning = observe_and_place_init(obj_type, location_group_name)
        status = await self._call_and_record("get_status", {}, messages, reasoning)

        gripper_state = status.get("gripper_state") if isinstance(status, dict) else (status[0] if isinstance(status, (list, tuple)) else status)

        if gripper_state == "open":
            return ("not_holding", messages)
        if gripper_state != obj_type:
            self.vars["$HELD_TYPE"] = gripper_state
            return ("wrong_type", messages)

        # 1.2 Get positions
        reasoning = observe_and_place_gripper_ready(obj_type)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Strategy: Identification via "String Parsing" simulation
        decoupling = self._decoupling_prefix("$Y")
        object_locations = expand_location(location_group_name, self.config)

        # 4. Occupancy Scan Strategy
        observe_positions = find_observe_positions_for_locations(object_locations, self.config)
        occupied_locations = set()
        inspected_positions = []
        covered = set()

        for i, obs_pos in enumerate(observe_positions):

            if i == 0:
                full_reasoning = decoupling + observe_and_place_first_move(
                    object_locations, observe_positions, obs_pos
                )
            else:
                remaining = self._compute_remaining(object_locations, inspected_positions)
                full_reasoning = observe_and_place_subsequent_move(
                    inspected_positions, obs_pos,
                    list(occupied_locations), remaining
                )

            # Move
            await self._call_and_record("move_to", {"pos": obs_pos}, messages, full_reasoning)

            # Locate
            reasoning = observe_and_place_scan(obs_pos, object_locations)
            shapes = await self._call_and_record("locate_shapes", {}, messages, reasoning)

            inspected_positions.append(obs_pos)

            if isinstance(shapes, dict):
                for loc in shapes.keys():
                    if loc in object_locations:
                        occupied_locations.add(loc)

            # Early stop: check if we already found an empty slot
            covered = set()
            for prev_pos in inspected_positions:
                vis = self._get_visible_locations(prev_pos, object_locations)
                covered.update(vis)
            confirmed_empty = [loc for loc in covered if loc not in occupied_locations]
            if confirmed_empty:
                break

        # 5. Analysis (Set Subtraction)
        empty_locations = [loc for loc in object_locations if loc not in occupied_locations
                          and loc in covered]
        if not empty_locations:
            # Fallback: any location not confirmed occupied
            empty_locations = [loc for loc in object_locations if loc not in occupied_locations]

        if not empty_locations:
             return ("all_occupied", messages)

        target_location = empty_locations[0]
        place_pos = find_place_position(obj_type, target_location, self.config)

        if place_pos:
            reasoning = observe_and_place_decide(
                object_locations, list(occupied_locations),
                empty_locations, target_location, place_pos
            )
            await self._call_and_record("move_to", {"pos": place_pos}, messages, reasoning)

            await self._call_and_record(
                "open_gripper", {}, messages, observe_and_place_open_gripper()
            )

        self.vars["$PLACED_LOCATION"] = target_location
        return ("success", messages)

    # ─── new routines ────────────────────────────────────────────────

    async def status_only(self) -> Tuple[str, List[ConversationMessage]]:
        """3.x — Single get_status call, return state info."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")

        reasoning = status_only_check()
        status = await self._call_and_record("get_status", {}, messages, reasoning)

        gripper = self._extract_gripper(status)
        position = self._extract_position(status)
        self.vars["$POSITION"] = position

        if gripper == "open":
            if x:
                return ("no_empty", messages)
            return ("empty", messages)
        else:
            self.vars["$HELD_TYPE"] = gripper
            if x:
                if gripper == x:
                    return ("yes", messages)
                return ("no_wrong", messages)
            return ("holding", messages)

    async def navigate_to(self) -> Tuple[str, List[ConversationMessage]]:
        """4.x — Navigate to a target position."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")

        reasoning = navigate_to_check_position()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        current_pos = self._extract_position(status)
        self.vars["$ORIGIN"] = current_pos

        reasoning = navigate_to_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling_y = self._decoupling_prefix("$Y")
        decoupling_z = self._decoupling_prefix("$Z")

        if x and y:
            # 4.5: Navigate to pick position for $X at $Y
            obj_locations = expand_location(y, self.config)
            target_loc = obj_locations[0] if obj_locations else y
            pick_pos = find_pick_position(x, target_loc, self.config)
            if pick_pos:
                reasoning = decoupling_y + navigate_to_pick_position(x, y, pick_pos)
                await self._call_and_record(
                    "move_to", {"pos": pick_pos}, messages, reasoning
                )
            return ("arrived", messages)

        elif y and z:
            # 4.4: Visit observation points for $Y and $Z (merged)
            y_locs = expand_location(y, self.config)
            z_locs = expand_location(z, self.config)
            merged_locs = list(dict.fromkeys(y_locs + z_locs))
            merged_obs = find_observe_positions_for_locations(merged_locs, self.config)

            inspected = []
            for i, obs_pos in enumerate(merged_obs):
                if i == 0:
                    reasoning = (
                        decoupling_y + decoupling_z
                        + navigate_to_merged_first_obs(y, z, merged_obs, obs_pos)
                    )
                else:
                    reasoning = navigate_to_merged_subsequent_obs(inspected, y, z, obs_pos)
                await self._call_and_record(
                    "move_to", {"pos": obs_pos}, messages, reasoning
                )
                inspected.append(obs_pos)

            return ("arrived", messages)

        elif y:
            # 4.2: Navigate to observation position for $Y
            y_locs = expand_location(y, self.config)
            obs_positions = find_observe_positions_for_locations(y_locs, self.config)
            if obs_positions:
                if len(obs_positions) == 1 and current_pos == obs_positions[0]:
                    return ("already_there", messages)

                inspected = []
                for i, obs_pos in enumerate(obs_positions):
                    if i == 0:
                        reasoning = decoupling_y + navigate_to_observe_first(y, obs_positions, obs_pos)
                    else:
                        reasoning = navigate_to_observe_subsequent(inspected, obs_pos)
                    await self._call_and_record(
                        "move_to", {"pos": obs_pos}, messages, reasoning
                    )
                    inspected.append(obs_pos)

            return ("arrived", messages)

        else:
            # 4.1: Navigate to home
            reasoning = navigate_to_home()
            await self._call_and_record(
                "move_to", {"pos": "home"}, messages, reasoning
            )
            return ("arrived", messages)

    async def observe_and_report(self) -> Tuple[str, List[ConversationMessage]]:
        """5.1-5.3, 5.7, 5.8 — Observe locations and report findings."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")

        reasoning = observe_and_report_check_status()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        self.vars["$POSITION"] = self._extract_position(status)

        reasoning = observe_and_report_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling_y = self._decoupling_prefix("$Y")
        y_locs = expand_location(y, self.config)

        if z:
            # 5.8: Compare Y and Z for $X (merged scan)
            decoupling_z = self._decoupling_prefix("$Z")
            z_locs = expand_location(z, self.config)

            # Merge all target locations for a single scan pass
            merged_locs = list(dict.fromkeys(y_locs + z_locs))
            purpose = (
                decoupling_y + decoupling_z
                + f"Checking '{y}' and '{z}' for '{x}'."
            )
            all_findings = await self._observe_locations(
                merged_locs, messages, purpose,
            )

            # Split findings back by group
            y_findings = {loc: obj for loc, obj in all_findings.items() if loc in y_locs}
            z_findings = {loc: obj for loc, obj in all_findings.items() if loc in z_locs}

            x_at_y = any(obj == x for obj in y_findings.values())
            x_at_z = any(obj == x for obj in z_findings.values())

            if x_at_y and x_at_z:
                return ("both", messages)
            elif x_at_y:
                return ("at_y", messages)
            elif x_at_z:
                return ("at_z", messages)
            else:
                return ("neither", messages)

        # Single group path (5.1-5.3, 5.7)
        y_findings = await self._observe_locations(
            y_locs, messages, decoupling_y + f"Looking at '{y}'.",
            early_stop_types=[x] if x else None,
            suppress_nontarget_findings=bool(x),
        )

        if not y_findings:
            return ("empty", messages)

        if x:
            # Check for $X at Y
            x_locations = [loc for loc, obj in y_findings.items() if obj == x]
            if x_locations:
                self.vars["$FOUND_LOCATIONS"] = ", ".join(x_locations)
                if len(y_locs) > 1:
                    self.vars["$REPORT"] = (
                        f"Yes, found {x} at {', '.join(x_locations)} in {y}."
                    )
                else:
                    self.vars["$REPORT"] = f"Yes, there is a {x} at {y}."
                return ("found", messages)
            else:
                found_types = list(set(y_findings.values()))
                self.vars["$FOUND_TYPE"] = found_types[0]
                items = ", ".join(
                    f"{obj} at {loc}" for loc, obj in y_findings.items()
                )
                if len(y_locs) > 1:
                    self.vars["$REPORT"] = f"No {x} found. Found: {items}."
                else:
                    self.vars["$REPORT"] = (
                        f"No, {y} has a {found_types[0]}, not a {x}."
                    )
                return ("different", messages)

        # No $X — just report what's at Y
        items = ", ".join(f"{obj} at {loc}" for loc, obj in y_findings.items())
        self.vars["$INVENTORY"] = items
        return ("found", messages)

    async def observe_and_report_all(self) -> Tuple[str, List[ConversationMessage]]:
        """5.4-5.6, 5.9 — Full inventory of a location group."""
        messages: List[ConversationMessage] = []
        y = self.vars.get("$Y", "")

        reasoning = observe_and_report_all_check_status()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        self.vars["$POSITION"] = self._extract_position(status)

        reasoning = observe_and_report_all_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling = self._decoupling_prefix("$Y")
        y_locs = expand_location(y, self.config)
        purpose = decoupling + observe_and_report_all_plan(y, y_locs, len(y_locs))
        findings = await self._observe_locations(
            y_locs, messages, purpose
        )

        total = len(y_locs)
        occupied = len(findings)
        empty_count = total - occupied

        self.vars["$TOTAL"] = str(total)
        self.vars["$COUNT"] = str(occupied)
        self.vars["$EMPTY_COUNT"] = str(empty_count)

        # Export empty/occupied location lists (used by 14.x final_messages)
        empty_locs = [loc for loc in y_locs if loc not in findings]
        occupied_locs = [loc for loc in y_locs if loc in findings]
        self.vars["$EMPTY_LOCATIONS"] = ", ".join(empty_locs) if empty_locs else "none"
        self.vars["$OCCUPIED_LOCATIONS"] = ", ".join(occupied_locs) if occupied_locs else "none"

        if occupied == 0:
            return ("all_empty", messages)

        # Per-location inventory
        inv_parts = []
        for loc in y_locs:
            if loc in findings:
                inv_parts.append(f"{loc}: {findings[loc]}")
            else:
                inv_parts.append(f"{loc}: empty")
        self.vars["$INVENTORY"] = "; ".join(inv_parts)

        # Per-type counts
        type_counts: Dict[str, int] = {}
        for obj in findings.values():
            type_counts[obj] = type_counts.get(obj, 0) + 1
        self.vars["$REPORT"] = "; ".join(
            f"{t}: {c}" for t, c in type_counts.items()
        )

        if empty_count > 0:
            return ("has_empty", messages)
        return ("all_full", messages)

    async def observe_and_pick_any(self) -> Tuple[str, List[ConversationMessage]]:
        """6.x — Pick with various conditional logic."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        w = self.vars.get("$W", "")
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")

        reasoning = observe_and_pick_any_check_gripper()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)
        if gripper != "open":
            return ("ask_user", messages)

        reasoning = observe_and_pick_any_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling_y = self._decoupling_prefix("$Y")

        # Determine context and early stop types
        if x and w:
            pick_context = observe_and_pick_any_context_xw(x, w, y)
            stop_types = [x, w]
        elif w and not x:
            pick_context = observe_and_pick_any_context_unless_w(w, y)
            stop_types = None
        elif z:
            pick_context = observe_and_pick_any_context_y_else_z(y, z)
            stop_types = None
        else:
            pick_context = observe_and_pick_any_context_whatever(y)
            stop_types = None

        y_locs = expand_location(y, self.config)
        y_findings = await self._observe_locations(
            y_locs, messages,
            decoupling_y + pick_context + f" Checking '{y}'.",
            early_stop_types=stop_types,
            suppress_nontarget_findings=bool(stop_types),
        )
        found_at_y = {
            loc: obj for loc, obj in y_findings.items() if loc in y_locs
        }

        if x and w:
            # 6.5-6.8: Pick $X or $W from Y
            x_loc = next(
                (loc for loc, obj in found_at_y.items() if obj == x), None
            )
            if x_loc:
                self.vars["$FOUND_TYPE"] = x
                await self._execute_pick(x, x_loc, messages)
                return ("found_x", messages)

            w_loc = next(
                (loc for loc, obj in found_at_y.items() if obj == w), None
            )
            if w_loc:
                self.vars["$FOUND_TYPE"] = w
                await self._execute_pick(w, w_loc, messages)
                return ("found_w", messages)

            if not found_at_y:
                return ("empty", messages)

            self.vars["$FOUND_TYPE"] = next(iter(found_at_y.values()))
            items = ", ".join(f"{obj} at {loc}" for loc, obj in found_at_y.items())
            self.vars["$FOUND_ITEMS"] = items
            return ("neither", messages)

        elif w and not x:
            # 6.9-6.11: Pick unless $W
            if not found_at_y:
                return ("empty", messages)

            loc, obj = next(iter(found_at_y.items()))
            self.vars["$FOUND_TYPE"] = obj
            if obj == w:
                return ("refused", messages)

            await self._execute_pick(obj, loc, messages)
            return ("success", messages)

        elif z:
            # 6.3-6.4: Pick from Y, else Z
            if found_at_y:
                loc, obj = next(iter(found_at_y.items()))
                self.vars["$FOUND_TYPE"] = obj
                await self._execute_pick(obj, loc, messages)
                return ("found_y", messages)

            decoupling_z = self._decoupling_prefix("$Z")
            z_locs = expand_location(z, self.config)
            z_findings = await self._observe_locations(
                z_locs, messages, decoupling_z + f"'{y}' is empty. Checking '{z}'."
            )
            found_at_z = {
                loc: obj for loc, obj in z_findings.items() if loc in z_locs
            }
            if found_at_z:
                loc, obj = next(iter(found_at_z.items()))
                self.vars["$FOUND_TYPE"] = obj
                await self._execute_pick(obj, loc, messages)
                return ("found_z", messages)

            return ("both_empty", messages)

        else:
            # 6.1-6.2: Pick whatever at Y
            if not found_at_y:
                return ("empty", messages)

            loc, obj = next(iter(found_at_y.items()))
            self.vars["$FOUND_TYPE"] = obj
            await self._execute_pick(obj, loc, messages)
            return ("success", messages)

    async def observe_and_pick_return_origin(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """7.x — Pick from Y (optionally $X only) and return to origin."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")

        reasoning = pick_return_origin_check_status()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)
        origin = self._extract_position(status)
        self.vars["$ORIGIN"] = origin

        if gripper != "open":
            return ("ask_user", messages)

        reasoning = pick_return_origin_load_positions(origin)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling = self._decoupling_prefix("$Y")
        context = pick_return_origin_context(x, y)
        y_locs = expand_location(y, self.config)
        y_findings = await self._observe_locations(
            y_locs, messages,
            decoupling + context + f" Checking '{y}'.",
            early_stop_types=[x] if x else None,
            suppress_nontarget_findings=bool(x),
        )
        found_at_y = {
            loc: obj for loc, obj in y_findings.items() if loc in y_locs
        }

        if x:
            # 7.1-7.5: Looking for specific type $X
            x_loc = next(
                (loc for loc, obj in found_at_y.items() if obj == x), None
            )
            if x_loc:
                self.vars["$FOUND_LOCATION"] = x_loc
                await self._execute_pick(x, x_loc, messages)

                reasoning = pick_return_origin_return_success(x, origin)
                await self._call_and_record(
                    "move_to", {"pos": origin}, messages, reasoning
                )
                return ("success", messages)

            elif not found_at_y:
                reasoning = pick_return_origin_return_empty(y, origin)
                await self._call_and_record(
                    "move_to", {"pos": origin}, messages, reasoning
                )
                return ("not_found", messages)

            else:
                found_type = next(iter(found_at_y.values()))
                self.vars["$FOUND_TYPE"] = found_type
                items = ", ".join(f"{obj} at {loc}" for loc, obj in found_at_y.items())
                self.vars["$FOUND_ITEMS"] = items
                reasoning = pick_return_origin_return_wrong_type(
                    found_type, y, x, origin, items
                )
                await self._call_and_record(
                    "move_to", {"pos": origin}, messages, reasoning
                )
                return ("wrong_type", messages)

        else:
            # 7.6-7.7: Pick whatever
            if not found_at_y:
                reasoning = pick_return_origin_return_any_empty(y, origin)
                await self._call_and_record(
                    "move_to", {"pos": origin}, messages, reasoning
                )
                return ("empty", messages)

            loc, obj = next(iter(found_at_y.items()))
            self.vars["$FOUND_TYPE"] = obj
            await self._execute_pick(obj, loc, messages)

            reasoning = pick_return_origin_return_any_success(obj, origin)
            await self._call_and_record(
                "move_to", {"pos": origin}, messages, reasoning
            )
            return ("success", messages)

    async def search_all_and_place(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """8.x — Search all locations for an empty spot and place."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")

        reasoning = search_all_and_place_check_gripper(x)
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)

        if gripper == "open":
            return ("not_holding", messages)
        if gripper != x:
            self.vars["$HELD_TYPE"] = gripper
            return ("wrong_type", messages)

        reasoning = search_all_and_place_load_positions(x)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # Determine scenario variant
        all_obj_locs = [
            loc for loc in self.config.object_locations
            if loc not in ("ATTACHED", "UNDEFINED")
        ]
        prefer_y = y and "placed_in_y" in self.draft.final_messages
        avoid_y = y and not prefer_y

        # Compute Y locations and decoupling if needed
        y_locs = expand_location(y, self.config) if y else []
        decoupling = self._decoupling_prefix("$Y") if y else ""

        # Scan all observe positions with early stopping
        all_observe = get_all_observe_positions(self.config)
        all_findings: Dict[str, str] = {}
        inspected: List[str] = []
        early_target = None

        for i, obs_pos in enumerate(all_observe):
            visible_locs = self._get_visible_locations(obs_pos)

            if i == 0:
                # Add scenario context on first move
                if prefer_y:
                    context = decoupling + search_all_place_context_prefer(x, y)
                elif avoid_y:
                    context = decoupling + search_all_place_context_avoid(x, y)
                else:
                    context = search_all_place_context_generic(x)
                reasoning = context + " " + search_all_and_place_first_scan(
                    all_observe, obs_pos, visible_locs
                )
            else:
                reasoning = search_all_and_place_subsequent_scan(
                    inspected, obs_pos, all_findings, visible_locs
                )

            await self._call_and_record(
                "move_to", {"pos": obs_pos}, messages, reasoning
            )

            reasoning = search_all_and_place_locate(obs_pos, visible_locs)
            shapes = await self._call_and_record(
                "locate_shapes", {}, messages, reasoning
            )
            inspected.append(obs_pos)
            if isinstance(shapes, dict):
                all_findings.update(shapes)

            # Early stopping: check if we have a valid empty target
            covered = set()
            for prev_pos in inspected:
                vis = self._get_visible_locations(prev_pos)
                covered.update(vis)
            observed_empty = [loc for loc in covered if loc not in all_findings
                              and loc in all_obj_locs]

            if prefer_y:
                y_empty_now = [loc for loc in observed_empty if loc in y_locs]
                if y_empty_now:
                    early_target = y_empty_now[0]
                    break
            elif avoid_y:
                non_y_empty_now = [loc for loc in observed_empty if loc not in y_locs]
                if non_y_empty_now:
                    early_target = non_y_empty_now[0]
                    break
            else:
                if observed_empty:
                    early_target = observed_empty[0]
                    break

        # Determine final target
        if early_target:
            self.vars["$PLACED_LOCATION"] = early_target
            await self._execute_place(x, early_target, messages)
            if prefer_y and early_target in y_locs:
                return ("placed_in_y", messages)
            elif prefer_y:
                return ("placed_elsewhere", messages)
            return ("success", messages)

        # No early stop — evaluate all findings
        if prefer_y:
            y_empty = [loc for loc in y_locs if loc not in all_findings]
            if y_empty:
                target = y_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("placed_in_y", messages)

            other_empty = [
                loc for loc in all_obj_locs
                if loc not in all_findings and loc not in y_locs
            ]
            if other_empty:
                target = other_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("placed_elsewhere", messages)

            return ("all_occupied", messages)

        elif avoid_y:
            non_y_empty = [
                loc for loc in all_obj_locs
                if loc not in all_findings and loc not in y_locs
            ]
            if non_y_empty:
                target = non_y_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("success", messages)

            return ("all_occupied", messages)

        else:
            empty = [loc for loc in all_obj_locs if loc not in all_findings]
            if empty:
                target = empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("success", messages)

            return ("all_occupied", messages)

    async def observe_and_place_with_fallback(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """9.x — Place at Y with fallback to Z, conditional on W, or strict."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")
        w = self.vars.get("$W", "")

        reasoning = place_with_fallback_check_gripper(x)
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)

        if gripper == "open":
            return ("not_holding", messages)
        if gripper != x:
            self.vars["$HELD_TYPE"] = gripper
            return ("wrong_type", messages)

        reasoning = place_with_fallback_load_positions(x)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling_y = self._decoupling_prefix("$Y")

        # Determine scenario context
        if w and z:
            context = place_fallback_context_conditional(x, y, z, w)
        elif z:
            context = place_fallback_context_yz(x, y, z)
        else:
            context = place_fallback_context_strict(x, y)

        # Observe Y
        y_locs = expand_location(y, self.config)
        y_findings = await self._observe_locations(
            y_locs, messages, decoupling_y + context + f" Checking '{y}'.",
            early_stop_types=[w] if w else None,
            suppress_nontarget_findings=bool(w),
        )

        if w:
            # 9.5-9.7: Conditional on W at Y
            w_at_y = any(obj == w for obj in y_findings.values())
            y_empty = [loc for loc in y_locs if loc not in y_findings]

            if not w_at_y:
                # Reason about non-W objects or empty state
                if y_findings:
                    found_type = next(iter(y_findings.values()))
                    found_loc = next(iter(y_findings.keys()))
                    non_w_reasoning = place_fallback_non_w_found(
                        y, w, found_type, found_loc, y_empty
                    )
                else:
                    non_w_reasoning = place_fallback_y_empty_no_w(y, w, y_empty)

                if y_empty:
                    target = y_empty[0]
                    self.vars["$PLACED_LOCATION"] = target
                    # Use non-W reasoning as prefix for placement move
                    place_pos = find_place_position(x, target, self.config)
                    if place_pos:
                        reasoning = non_w_reasoning + f" Place position: '{place_pos}'. Moving there."
                        await self._call_and_record(
                            "move_to", {"pos": place_pos}, messages, reasoning
                        )
                        await self._call_and_record(
                            "open_gripper", {}, messages, execute_place_open()
                        )
                    return ("placed_y", messages)
                return ("both_occupied", messages)

            # W is at Y → try Z
            if z:
                decoupling_z = self._decoupling_prefix("$Z")
                z_locs = expand_location(z, self.config)
                z_findings = await self._observe_locations(
                    z_locs, messages,
                    decoupling_z + f"'{y}' has '{w}'. Redirect triggered. Checking '{z}'."
                )
                z_empty = [loc for loc in z_locs if loc not in z_findings]
                if z_empty:
                    target = z_empty[0]
                    self.vars["$PLACED_LOCATION"] = target
                    await self._execute_place(x, target, messages)
                    return ("placed_z", messages)

            return ("both_occupied", messages)

        elif z:
            # 9.1-9.3: Place at Y, else Z
            y_empty = [loc for loc in y_locs if loc not in y_findings]

            if y_empty:
                target = y_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("placed_primary", messages)

            decoupling_z = self._decoupling_prefix("$Z")
            z_locs = expand_location(z, self.config)
            z_findings = await self._observe_locations(
                z_locs, messages, decoupling_z + f"'{y}' is occupied. Checking '{z}'."
            )
            z_empty = [loc for loc in z_locs if loc not in z_findings]

            if z_empty:
                target = z_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("placed_fallback", messages)

            return ("both_occupied", messages)

        else:
            # 9.4: Strict Y only
            y_empty = [loc for loc in y_locs if loc not in y_findings]

            if y_empty:
                target = y_empty[0]
                self.vars["$PLACED_LOCATION"] = target
                await self._execute_place(x, target, messages)
                return ("placed", messages)

            self.vars["$FOUND_TYPE"] = next(
                iter(y_findings.values()), "unknown"
            )
            items = ", ".join(f"{obj} at {loc}" for loc, obj in y_findings.items())
            self.vars["$FOUND_ITEMS"] = items
            return ("occupied", messages)

    async def pick_and_place(self) -> Tuple[str, List[ConversationMessage]]:
        """10.x — Pick from Y then place at Z."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")

        reasoning = pick_and_place_check_gripper()
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)

        if gripper != "open":
            return ("ask_user", messages)

        reasoning = pick_and_place_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        decoupling_y = self._decoupling_prefix("$Y")
        context = pick_and_place_context(x, y, z)

        # === PICK PHASE ===
        y_locs = expand_location(y, self.config)
        y_findings = await self._observe_locations(
            y_locs, messages, decoupling_y + context + f" Checking '{y}' for pick."
        )
        found_at_y = {
            loc: obj for loc, obj in y_findings.items() if loc in y_locs
        }

        if x:
            # 10.1-10.6: Pick $X from Y
            x_loc = next(
                (loc for loc, obj in found_at_y.items() if obj == x), None
            )
            if not x_loc:
                return ("pick_failed", messages)

            self.vars["$FOUND_LOCATION"] = x_loc
            await self._execute_pick(x, x_loc, messages)
            picked_type = x
            picked_from = x_loc
        else:
            # 10.7-10.9: Pick whatever from Y
            if not found_at_y:
                return ("empty_source", messages)

            loc, obj = next(iter(found_at_y.items()))
            self.vars["$FOUND_TYPE"] = obj
            self.vars["$FOUND_LOCATION"] = loc
            await self._execute_pick(obj, loc, messages)
            picked_type = obj
            picked_from = loc

        # === PLACE PHASE ===
        decoupling_z = self._decoupling_prefix("$Z")
        transition = pick_and_place_transition(picked_type, picked_from, z)
        z_locs = expand_location(z, self.config)
        z_findings = await self._observe_locations(
            z_locs, messages, decoupling_z + transition
        )
        z_empty = [loc for loc in z_locs if loc not in z_findings]

        has_return_fallback = "returned" in self.draft.final_messages

        if z_empty:
            target = z_empty[0]
            self.vars["$PLACED_LOCATION"] = target
            await self._execute_place(picked_type, target, messages)
            return ("success", messages)

        # Z full
        if has_return_fallback:
            # 10.4-10.6: Return to Y
            place_back = find_place_position(
                picked_type, picked_from, self.config
            )
            if place_back:
                reasoning = pick_and_place_return_to_source(picked_type, z, y)
                await self._call_and_record(
                    "move_to", {"pos": place_back}, messages, reasoning
                )
                await self._call_and_record(
                    "open_gripper", {}, messages,
                    pick_and_place_return_open_gripper()
                )
            return ("returned", messages)

        return ("place_failed", messages)

    # ─── new routines (12.x, 13.x, 15.x) ─────────────────────────────────

    async def observe_conditional_pick(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """12.x — Check Y for X. If found, pick. Otherwise report."""
        messages: List[ConversationMessage] = []
        x = self.vars.get("$X", "")
        y = self.vars.get("$Y", "")

        # 1. Check gripper
        reasoning = observe_conditional_pick_init(x, y)
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)
        if gripper != "open":
            return ("ask_user", messages)

        # 2. Load positions
        reasoning = observe_conditional_pick_gripper_ready(x, y)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Observe Y
        decoupling = self._decoupling_prefix("$Y")
        context = observe_conditional_pick_context(x, y)
        y_locs = expand_location(y, self.config)

        findings = await self._observe_locations(
            y_locs, messages,
            decoupling + context,
            early_stop_types=[x],
        )
        found_at_y = {
            loc: obj for loc, obj in findings.items() if loc in y_locs
        }

        # 4. Branch on findings
        x_loc = next(
            (loc for loc, obj in found_at_y.items() if obj == x), None
        )
        if x_loc:
            # X found → pick it
            self.vars["$FOUND_LOCATION"] = x_loc
            pick_pos = find_pick_position(x, x_loc, self.config)
            if pick_pos:
                reasoning = (
                    observe_conditional_pick_found_x(x, x_loc)
                    + " " + execute_pick_move(x, x_loc, pick_pos)
                )
                await self._call_and_record(
                    "move_to", {"pos": pick_pos}, messages, reasoning
                )
                reasoning = execute_pick_close(pick_pos)
                await self._call_and_record(
                    "close_gripper", {}, messages, reasoning
                )
            return ("picked", messages)

        if found_at_y:
            # Different type found
            first_type = next(iter(found_at_y.values()))
            self.vars["$FOUND_TYPE"] = first_type
            items = ", ".join(f"{obj} at {loc}" for loc, obj in found_at_y.items())
            self.vars["$FOUND_ITEMS"] = items
            return ("different", messages)

        # Y is empty
        return ("empty", messages)

    async def compare_inventories(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """13.x — Compare object counts across Y and Z (merged scan)."""
        messages: List[ConversationMessage] = []
        y = self.vars.get("$Y", "")
        z = self.vars.get("$Z", "")

        # 1. Status check
        reasoning = compare_inventories_check_status()
        await self._call_and_record("get_status", {}, messages, reasoning)

        # 2. Load positions
        reasoning = compare_inventories_load_positions()
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Decouple both groups upfront and expand locations
        decoupling_y = self._decoupling_prefix("$Y")
        decoupling_z = self._decoupling_prefix("$Z")
        y_locs = expand_location(y, self.config)
        z_locs = expand_location(z, self.config)

        plan = compare_inventories_plan(y, z, y_locs, z_locs)

        # 4. Merge all target locations (deduplicated, order-preserving)
        merged_locs = list(dict.fromkeys(y_locs + z_locs))

        # 5. Single merged scan
        purpose = decoupling_y + decoupling_z + plan
        all_findings = await self._observe_locations(
            merged_locs, messages, purpose
        )

        # 6. Split findings back by group
        y_findings = {loc: obj for loc, obj in all_findings.items() if loc in y_locs}
        z_findings = {loc: obj for loc, obj in all_findings.items() if loc in z_locs}

        y_count = len(y_findings)
        z_count = len(z_findings)

        # 7. Compute results
        self.vars["$Y_COUNT"] = str(y_count)
        self.vars["$Z_COUNT"] = str(z_count)

        counts = {y: y_count, z: z_count}
        most = max(counts, key=counts.get)
        emptiest = min(counts, key=counts.get)
        self.vars["$MOST"] = most
        self.vars["$EMPTIEST"] = emptiest

        return ("compared", messages)

    async def place_implicit_type(
        self,
    ) -> Tuple[str, List[ConversationMessage]]:
        """15.x — Place whatever is held at Y (no type check)."""
        messages: List[ConversationMessage] = []
        y = self.vars.get("$Y", "")

        # 1. Check gripper — accept ANY held type
        reasoning = place_implicit_type_init(y)
        status = await self._call_and_record("get_status", {}, messages, reasoning)
        gripper = self._extract_gripper(status)

        if gripper == "open":
            return ("not_holding", messages)

        held_type = gripper
        self.vars["$HELD_TYPE"] = held_type

        # 2. Load positions
        reasoning = place_implicit_type_gripper_ready(held_type)
        await self._call_and_record("get_positions", {}, messages, reasoning)

        # 3. Scan Y for empty slots (reuse observe_and_place prompts)
        decoupling = self._decoupling_prefix("$Y")
        context = place_implicit_type_context(held_type, y)
        y_locs = expand_location(y, self.config)

        obs_positions = find_observe_positions_for_locations(y_locs, self.config)
        occupied_locations = set()
        inspected_positions = []
        covered = set()

        for i, obs_pos in enumerate(obs_positions):
            if i == 0:
                full_reasoning = (
                    decoupling + context + " "
                    + observe_and_place_first_move(y_locs, obs_positions, obs_pos)
                )
            else:
                remaining = self._compute_remaining(y_locs, inspected_positions)
                full_reasoning = observe_and_place_subsequent_move(
                    inspected_positions, obs_pos,
                    list(occupied_locations), remaining
                )

            await self._call_and_record(
                "move_to", {"pos": obs_pos}, messages, full_reasoning
            )

            reasoning = observe_and_place_scan(obs_pos, y_locs)
            shapes = await self._call_and_record(
                "locate_shapes", {}, messages, reasoning
            )

            inspected_positions.append(obs_pos)

            if isinstance(shapes, dict):
                for loc in shapes.keys():
                    if loc in y_locs:
                        occupied_locations.add(loc)

            # Early stop on empty slot
            covered = set()
            for prev_pos in inspected_positions:
                vis = self._get_visible_locations(prev_pos, y_locs)
                covered.update(vis)
            confirmed_empty = [
                loc for loc in covered if loc not in occupied_locations
            ]
            if confirmed_empty:
                break

        # 4. Find empty slot
        empty_locations = [
            loc for loc in y_locs
            if loc not in occupied_locations and loc in covered
        ]
        if not empty_locations:
            empty_locations = [
                loc for loc in y_locs if loc not in occupied_locations
            ]

        if not empty_locations:
            return ("all_occupied", messages)

        # 5. Place
        target_location = empty_locations[0]
        place_pos = find_place_position(held_type, target_location, self.config)

        if place_pos:
            reasoning = place_implicit_type_decide(
                held_type, empty_locations, target_location, place_pos
            )
            await self._call_and_record(
                "move_to", {"pos": place_pos}, messages, reasoning
            )
            await self._call_and_record(
                "open_gripper", {}, messages, observe_and_place_open_gripper()
            )

        self.vars["$PLACED_LOCATION"] = target_location
        return ("success", messages)
