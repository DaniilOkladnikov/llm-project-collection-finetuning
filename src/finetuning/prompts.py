"""Centralized reasoning prompts and system prompt for fine-tuning conversations.

All reasoning strings used in tool_routines.py are extracted here as named
functions, grouped by routine.  Each function accepts only the parameters it
needs and returns a plain string chosen randomly from several variants to
increase diversity in the training data.
"""

import random
from typing import Dict, List

# --- SYSTEM PROMPT -------------------------------------------------------------

SYSTEM_PROMPT = """You are a precise and cautious robot control assistant.
Your job is to decide which tool to call next so that the robot interacts safely with objects.

**General Action Rules**
- Robot must always start with calling get_status and get_positions
- How to locate objects:
    1. Go to position where you can locate objects from
    2. Call locate_shapes tool
- How to pick up an object:
    1. Go to vantage point
    2. Locate object precisely with perception tools
    3. Go to position suitable for picking this object
    4. Close the gripper
- How to place an object:
    1. Go to vantage point
    2. Use perception tools to find empty location or check if the target location is empty
    3. If target location is empty, go to position suitable for releasing this object
    4. Open the gripper
"""

# --- SHARED HELPERS ------------------------------------------------------------
# Functions used by _observe_locations, _execute_pick, _execute_place


def decouple_location_group(
    group_name: str,
    expanded_locations: List[str],
    sample_position_names: List[str],
) -> str:
    """Reasoning to explain how the model deduced locations from position names."""
    samples_str = ", ".join(f"'{p}'" for p in sample_position_names[:6])
    return random.choice([
        (
            f"The user referenced '{group_name}'. "
            f"From the position list, I can see positions like: {samples_str}. "
            f"These position names indicate that '{group_name}' contains the "
            f"following locations: {expanded_locations}."
        ),
        (
            f"The user mentioned '{group_name}'. "
            f"Looking at the position list, I notice entries such as {samples_str}. "
            f"This tells me '{group_name}' maps to these locations: {expanded_locations}."
        ),
        (
            f"'{group_name}' was referenced by the user. "
            f"Checking the position list, I see names like {samples_str}. "
            f"From these names I can deduce that '{group_name}' includes: {expanded_locations}."
        ),
        (
            f"The user said '{group_name}'. "
            f"In the position list I find entries such as {samples_str}. "
            f"These entries reveal that '{group_name}' covers: {expanded_locations}."
        ),
        (
            f"Interpreting '{group_name}' from the user's request. "
            f"The position list contains {samples_str}, among others. "
            f"So '{group_name}' corresponds to locations: {expanded_locations}."
        ),
    ])


def decouple_simple_location(
    location: str,
    sample_position_names: List[str],
) -> str:
    """Reasoning to confirm a simple object location from position names."""
    samples_str = ", ".join(f"'{p}'" for p in sample_position_names[:6])
    return random.choice([
        (
            f"The user mentioned '{location}'. "
            f"From the position list, I can see positions like: {samples_str}. "
            f"This confirms that '{location}' is a valid location."
        ),
        (
            f"'{location}' was referenced. "
            f"Checking the position list, I find entries such as {samples_str}. "
            f"This verifies '{location}' as a known location."
        ),
        (
            f"The user specified '{location}'. "
            f"I see matching positions in the list: {samples_str}. "
            f"'{location}' is confirmed as a valid location."
        ),
        (
            f"Looking up '{location}' in the position list. "
            f"Found related positions: {samples_str}. "
            f"This confirms '{location}' exists in the environment."
        ),
        (
            f"The user wants '{location}'. "
            f"The position list has entries like {samples_str}, "
            f"which confirms '{location}' is a recognized location."
        ),
    ])


def observe_locations_first_move(
    target_locations: List[str],
    obs_positions: List[str],
    obs_pos: str,
    purpose: str,
) -> str:
    """First vantage-point move inside _observe_locations."""
    p = f"{purpose} " if purpose else ""
    return random.choice([
        (
            f"{p}From the positions list, scanning for observation points covering "
            f"{target_locations}... Found vantage points: {obs_positions}. "
            f"Moving to '{obs_pos}'."
        ),
        (
            f"{p}Checking the positions list for viewpoints that cover "
            f"{target_locations}. Identified: {obs_positions}. "
            f"Heading to '{obs_pos}' first."
        ),
        (
            f"{p}I need to observe {target_locations}. "
            f"From the positions list, suitable observation points are {obs_positions}. "
            f"Going to '{obs_pos}'."
        ),
        (
            f"{p}Looking through the positions list for vantage points over "
            f"{target_locations}. Found {obs_positions}. "
            f"Navigating to '{obs_pos}'."
        ),
        (
            f"{p}From the positions list, observation points for "
            f"{target_locations} are {obs_positions}. "
            f"Starting with '{obs_pos}'."
        ),
    ])


def observe_locations_subsequent_move(
    inspected: List[str],
    obs_pos: str,
    findings_so_far: Dict[str, str] = None,
    remaining_locations: List[str] = None,
    suppress_nontarget_findings: bool = False,
) -> str:
    """Subsequent vantage-point move inside _observe_locations with memory."""
    intro = random.choice([
        f"Scanned from {inspected}.",
        f"Already visited {inspected}.",
        f"Checked from {inspected}.",
        f"Completed scanning at {inspected}.",
        f"Finished inspecting from {inspected}.",
    ])
    parts = [intro]
    if suppress_nontarget_findings:
        parts.append(random.choice([
            "Have not found the target yet.",
            "Target not spotted yet.",
            "No sign of the target so far.",
            "Still searching for the target.",
            "The target has not appeared yet.",
        ]))
    elif findings_so_far:
        found_items = [f"'{obj}' at '{loc}'" for loc, obj in findings_so_far.items()]
        parts.append(random.choice([
            f"Found so far: {', '.join(found_items)}.",
            f"Discovered: {', '.join(found_items)}.",
            f"Spotted: {', '.join(found_items)}.",
            f"Objects detected: {', '.join(found_items)}.",
            f"Already observed: {', '.join(found_items)}.",
        ]))
    else:
        parts.append(random.choice([
            "Nothing found so far.",
            "No objects detected yet.",
            "All locations empty so far.",
            "Haven't spotted anything yet.",
            "No findings yet.",
        ]))
    if remaining_locations:
        parts.append(random.choice([
            f"Still need to check: {remaining_locations}.",
            f"Remaining to inspect: {remaining_locations}.",
            f"Left to scan: {remaining_locations}.",
            f"Have not checked yet: {remaining_locations}.",
            f"Unchecked locations: {remaining_locations}.",
        ]))
    parts.append(random.choice([
        f"Moving to next vantage point: '{obs_pos}'.",
        f"Proceeding to '{obs_pos}'.",
        f"Heading to the next observation point: '{obs_pos}'.",
        f"Continuing to '{obs_pos}'.",
        f"Next stop: '{obs_pos}'.",
    ]))
    return " ".join(parts)


def observe_locations_scan(
    obs_pos: str,
    visible_locations: List[str] = None,
) -> str:
    """Scan reasoning at a vantage point inside _observe_locations."""
    if visible_locations:
        return random.choice([
            f"At '{obs_pos}'. This position covers {visible_locations}. Scanning.",
            f"Arrived at '{obs_pos}'. I can see {visible_locations} from here. Running scan.",
            f"Now at '{obs_pos}', which covers {visible_locations}. Scanning area.",
            f"Positioned at '{obs_pos}'. Visible locations: {visible_locations}. Initiating scan.",
            f"At vantage point '{obs_pos}'. Coverage: {visible_locations}. Scanning now.",
        ])
    return random.choice([
        f"At '{obs_pos}'. Scanning area.",
        f"Arrived at '{obs_pos}'. Running scan.",
        f"Now at '{obs_pos}'. Scanning the visible area.",
        f"Positioned at '{obs_pos}'. Initiating scan.",
        f"At '{obs_pos}'. Looking around.",
    ])


def execute_pick_move(obj_type: str, location: str, pick_pos: str) -> str:
    """Reasoning before moving to the pick position in _execute_pick."""
    return random.choice([
        (
            f"Found '{obj_type}' at '{location}'. "
            f"Pick position: '{pick_pos}'. Moving there."
        ),
        (
            f"'{obj_type}' spotted at '{location}'. "
            f"The pick position is '{pick_pos}'. Heading there now."
        ),
        (
            f"Located '{obj_type}' at '{location}'. "
            f"Moving to pick position '{pick_pos}'."
        ),
        (
            f"Detected '{obj_type}' at '{location}'. "
            f"Navigating to '{pick_pos}' for pickup."
        ),
        (
            f"'{obj_type}' is at '{location}'. "
            f"Going to '{pick_pos}' to pick it up."
        ),
    ])


def execute_pick_close(pick_pos: str) -> str:
    """Reasoning before closing the gripper in _execute_pick."""
    return random.choice([
        f"Aligned at '{pick_pos}'. Closing gripper.",
        f"In position at '{pick_pos}'. Closing the gripper now.",
        f"At '{pick_pos}', ready to grab. Closing gripper.",
        f"Positioned at '{pick_pos}'. Engaging gripper.",
        f"Reached '{pick_pos}'. Gripping the object.",
    ])


def execute_place_move(location: str, place_pos: str) -> str:
    """Reasoning before moving to the place position in _execute_place."""
    return random.choice([
        (
            f"Target '{location}' is empty. "
            f"Place position: '{place_pos}'. Moving there."
        ),
        (
            f"'{location}' is available. "
            f"Heading to place position '{place_pos}'."
        ),
        (
            f"Confirmed '{location}' is empty. "
            f"Navigating to '{place_pos}' to place the object."
        ),
        (
            f"'{location}' has an open slot. "
            f"Moving to '{place_pos}' for placement."
        ),
        (
            f"The target location '{location}' is free. "
            f"Going to '{place_pos}' to release the object."
        ),
    ])


def execute_place_open() -> str:
    """Reasoning before opening the gripper in _execute_place."""
    return random.choice([
        "Opening gripper to release object.",
        "Releasing the object by opening the gripper.",
        "Gripper open - dropping the object into position.",
        "Opening the gripper now to let go of the object.",
        "Time to release. Opening gripper.",
    ])


def early_stop_found_empty(
    empty_loc: str,
    inspected: List[str],
    total_observe: int,
) -> str:
    """Reasoning when stopping a scan early after finding a valid empty location."""
    return random.choice([
        (
            f"After scanning from {inspected} ({len(inspected)} of {total_observe} "
            f"observation points), I confirmed that '{empty_loc}' is empty. "
            f"No need to continue scanning the remaining positions."
        ),
        (
            f"Scanned from {inspected} ({len(inspected)}/{total_observe} vantage points). "
            f"'{empty_loc}' is empty - stopping early since I found a valid spot."
        ),
        (
            f"Checked {len(inspected)} of {total_observe} observation points ({inspected}). "
            f"Found '{empty_loc}' is empty. Skipping the rest."
        ),
        (
            f"After visiting {inspected}, '{empty_loc}' is confirmed empty. "
            f"That's {len(inspected)} out of {total_observe} - no need to check more."
        ),
        (
            f"'{empty_loc}' is empty, confirmed after scanning from {inspected}. "
            f"Only needed {len(inspected)} of {total_observe} observation points."
        ),
    ])


# --- observe_and_pick ----------------------------------------------------------


def observe_and_pick_init(obj_type: str, location: str) -> str:
    """Initial status check reasoning."""
    return random.choice([
        f"I need to pick up the '{obj_type}' from '{location}'. First, checking gripper state.",
        f"Task: pick up '{obj_type}' from '{location}'. Let me check my current status.",
        f"The goal is to grab '{obj_type}' from '{location}'. Checking my state first.",
        f"I have to retrieve '{obj_type}' from '{location}'. Starting with a status check.",
        f"Need to get '{obj_type}' from '{location}'. Let me verify gripper state first.",
    ])


def observe_and_pick_gripper_ready() -> str:
    """Reasoning after gripper confirmed open."""
    return random.choice([
        "Gripper is open and ready. Now I need to load available positions.",
        "Good, gripper is open. Loading the position list next.",
        "Gripper confirmed open. Time to get the available positions.",
        "Gripper state: open. Proceeding to load positions.",
        "The gripper is free. Let me fetch the available positions.",
    ])


def observe_and_pick_first_move(
    location: str,
    obj_type: str,
    object_locations: List[str],
    observe_positions: List[str],
    obs_pos: str,
) -> str:
    """First move in the search loop - parsing and planning."""
    return random.choice([
        (
            f"Scanning position list for '{location}'... "
            f"Found matching target locations: {object_locations}. "
            f"To locate the '{obj_type}', I need to inspect these areas. "
            f"I have identified valid vantage points: {observe_positions}. "
            f"Moving to {obs_pos} to scan."
        ),
        (
            f"From the positions list, '{location}' maps to {object_locations}. "
            f"I need to find the '{obj_type}' there. "
            f"Observation points for these locations: {observe_positions}. "
            f"Starting at '{obs_pos}'."
        ),
        (
            f"Looking up '{location}' in the position list - "
            f"target locations are {object_locations}. "
            f"To find '{obj_type}', I'll scan from {observe_positions}. "
            f"Heading to '{obs_pos}' first."
        ),
        (
            f"Position list shows '{location}' includes {object_locations}. "
            f"I'll search for '{obj_type}' by visiting vantage points {observe_positions}. "
            f"Going to '{obs_pos}'."
        ),
        (
            f"Parsed positions for '{location}': {object_locations}. "
            f"Vantage points to check for '{obj_type}': {observe_positions}. "
            f"Navigating to '{obs_pos}' to begin scanning."
        ),
    ])


def observe_and_pick_subsequent_move(
    inspected_positions: List[str],
    obj_type: str,
    obs_pos: str,
    remaining_locations: List[str] = None,
) -> str:
    """Subsequent move in the search loop - progress update."""
    parts = [random.choice([
        f"I have already inspected from {inspected_positions} and did not find the '{obj_type}'.",
        f"Checked {inspected_positions} - no '{obj_type}' spotted.",
        f"Scanned from {inspected_positions} without finding '{obj_type}'.",
        f"Visited {inspected_positions} so far. No '{obj_type}' yet.",
        f"No sign of '{obj_type}' after scanning from {inspected_positions}.",
    ])]
    if remaining_locations:
        parts.append(random.choice([
            f"Still need to check: {remaining_locations}.",
            f"Remaining to inspect: {remaining_locations}.",
            f"Left to scan: {remaining_locations}.",
            f"Unchecked locations: {remaining_locations}.",
            f"Have not looked at: {remaining_locations}.",
        ]))
    parts.append(random.choice([
        f"Proceeding to the next vantage point: '{obs_pos}'. Moving there now.",
        f"Moving to '{obs_pos}' to continue the search.",
        f"Heading to next observation point: '{obs_pos}'.",
        f"Continuing search at '{obs_pos}'.",
        f"Next vantage point is '{obs_pos}'. Going there.",
    ]))
    return " ".join(parts)


def observe_and_pick_scan(
    obs_pos: str,
    obj_type: str,
    visible_locations: List[str] = None,
) -> str:
    """Scan reasoning at a vantage point with visibility info."""
    if visible_locations:
        return random.choice([
            f"I am at '{obs_pos}'. From here I can see {visible_locations}. Scanning for the '{obj_type}'.",
            f"At '{obs_pos}', covering {visible_locations}. Looking for '{obj_type}'.",
            f"Positioned at '{obs_pos}'. Visible locations: {visible_locations}. Searching for '{obj_type}'.",
            f"Now at '{obs_pos}', which covers {visible_locations}. Scanning for '{obj_type}'.",
            f"At vantage point '{obs_pos}'. I can observe {visible_locations}. Scanning for '{obj_type}'.",
        ])
    return random.choice([
        f"I am at '{obs_pos}'. Scanning the visible area to find the '{obj_type}'.",
        f"At '{obs_pos}'. Looking for '{obj_type}'.",
        f"Positioned at '{obs_pos}'. Scanning for '{obj_type}'.",
        f"At '{obs_pos}'. Searching for any '{obj_type}' in view.",
        f"Now at '{obs_pos}'. Running scan to detect '{obj_type}'.",
    ])


def observe_and_pick_move_to_pick(
    obj_type: str,
    found_location: str,
    pick_pos: str,
) -> str:
    """Reasoning before moving to the pick position after finding the object."""
    return random.choice([
        (
            f"Success. I found the '{obj_type}' at '{found_location}'. "
            f"Scanning the position list for a suitable pick position... "
            f"Found '{pick_pos}'. Moving to that position."
        ),
        (
            f"Found '{obj_type}' at '{found_location}'. "
            f"From the position list, the pick position is '{pick_pos}'. "
            f"Heading there now."
        ),
        (
            f"'{obj_type}' located at '{found_location}'. "
            f"Looking up pick position in the list... '{pick_pos}'. "
            f"Moving to pick it up."
        ),
        (
            f"Spotted the '{obj_type}' at '{found_location}'. "
            f"The position list gives me pick position '{pick_pos}'. "
            f"Navigating there."
        ),
        (
            f"Target '{obj_type}' found at '{found_location}'. "
            f"Pick position: '{pick_pos}'. Going there to grab it."
        ),
    ])


def observe_and_pick_close_gripper(pick_pos: str) -> str:
    """Reasoning before closing the gripper to acquire the object."""
    return random.choice([
        f"I am aligned at '{pick_pos}'. Closing gripper to acquire the object.",
        f"At '{pick_pos}'. Gripping the object now.",
        f"In position at '{pick_pos}'. Closing gripper to grab it.",
        f"Positioned at '{pick_pos}', ready to pick. Closing gripper.",
        f"Reached '{pick_pos}'. Engaging the gripper to pick up the object.",
    ])


# --- search_all_and_pick ------------------------------------------------------


def search_all_and_pick_init(obj_type: str) -> str:
    """Initial status check reasoning for global search."""
    return random.choice([
        (
            f"I need to find and pick up a '{obj_type}', but I do not have a specific location. "
            f"I must perform a global search of the environment. First, checking status."
        ),
        (
            f"Task: locate and pick up '{obj_type}' - no location specified. "
            f"I'll need to search the entire environment. Checking status first."
        ),
        (
            f"I have to find a '{obj_type}' somewhere in the environment. "
            f"Since no location was given, I'll do a full search. Starting with status check."
        ),
        (
            f"Need to pick up '{obj_type}' but I don't know where it is. "
            f"Will search all locations. Let me check my current state."
        ),
        (
            f"The goal is to find '{obj_type}' anywhere in the environment and pick it up. "
            f"Beginning with a status check."
        ),
    ])


def search_all_and_pick_gripper_ready() -> str:
    """Reasoning after gripper confirmed open."""
    return random.choice([
        "Gripper is open and ready. Now I need to load available positions.",
        "Good, gripper is open. Loading positions for the global search.",
        "Gripper confirmed open. Fetching the positions list.",
        "Gripper is free. Let me load the available positions.",
        "Gripper state: open. Proceeding to load positions.",
    ])


def search_all_and_pick_first_move(
    all_observe: List[str],
    obj_type: str,
    obs_pos: str,
) -> str:
    """First move in the global search loop."""
    return random.choice([
        (
            f"Scanning the position list for general observation points... "
            f"I have identified the following vantage points that cover the scene: {all_observe}. "
            f"I will visit them sequentially to look for the '{obj_type}'. "
            f"Moving to vantage point '{obs_pos}'."
        ),
        (
            f"From the position list, the observation points are: {all_observe}. "
            f"I'll visit each one to find '{obj_type}'. "
            f"Starting at '{obs_pos}'."
        ),
        (
            f"Identified all observation points from the position list: {all_observe}. "
            f"I need to search them one by one for '{obj_type}'. "
            f"Heading to '{obs_pos}' first."
        ),
        (
            f"The position list reveals these observation points: {all_observe}. "
            f"Plan: visit each to locate '{obj_type}'. "
            f"Going to '{obs_pos}'."
        ),
        (
            f"Observation vantage points from position list: {all_observe}. "
            f"Will scan each for '{obj_type}'. "
            f"Navigating to '{obs_pos}'."
        ),
    ])


def search_all_and_pick_subsequent_move(
    inspected_positions: List[str],
    obs_pos: str,
) -> str:
    """Subsequent move in the global search loop."""
    return random.choice([
        (
            f"I have already scanned from {inspected_positions} and did not find the target object. "
            f"Proceeding to the next vantage point in the plan: '{obs_pos}'."
        ),
        (
            f"Checked {inspected_positions} - no target found yet. "
            f"Moving on to '{obs_pos}'."
        ),
        (
            f"Scanned from {inspected_positions} without finding the target. "
            f"Heading to '{obs_pos}' to continue searching."
        ),
        (
            f"Visited {inspected_positions} so far, target not found. "
            f"Next observation point: '{obs_pos}'."
        ),
        (
            f"No luck at {inspected_positions}. "
            f"Continuing the search at '{obs_pos}'."
        ),
    ])


def search_all_and_pick_scan(
    obs_pos: str,
    obj_type: str,
    visible_locations: List[str] = None,
) -> str:
    """Scan reasoning at a vantage point during global search."""
    if visible_locations:
        return random.choice([
            f"I am at '{obs_pos}'. From here I can see {visible_locations}. Scanning to detect any '{obj_type}'.",
            f"At '{obs_pos}', covering {visible_locations}. Looking for '{obj_type}'.",
            f"Positioned at '{obs_pos}'. Visible: {visible_locations}. Searching for '{obj_type}'.",
            f"At vantage point '{obs_pos}'. I can observe {visible_locations}. Scanning for '{obj_type}'.",
            f"Now at '{obs_pos}'. This covers {visible_locations}. Running detection for '{obj_type}'.",
        ])
    return random.choice([
        f"I am at '{obs_pos}'. Scanning area to detect any '{obj_type}'.",
        f"At '{obs_pos}'. Looking for '{obj_type}'.",
        f"Now at '{obs_pos}'. Scanning for '{obj_type}'.",
        f"Positioned at '{obs_pos}'. Searching for '{obj_type}'.",
        f"At '{obs_pos}'. Running scan for '{obj_type}'.",
    ])


def search_all_and_pick_move_to_pick(
    obj_type: str,
    found_location: str,
    pick_pos: str,
) -> str:
    """Reasoning before moving to the pick position after a successful global search."""
    return random.choice([
        (
            f"Search successful. I located the '{obj_type}' at '{found_location}'. "
            f"Scanning position list for a suitable pick position... "
            f"Found '{pick_pos}'. Moving there to acquire the object."
        ),
        (
            f"Found '{obj_type}' at '{found_location}'. "
            f"From the position list, pick position is '{pick_pos}'. "
            f"Going there now."
        ),
        (
            f"Target '{obj_type}' located at '{found_location}'. "
            f"Position list gives pick position '{pick_pos}'. "
            f"Heading to '{pick_pos}'."
        ),
        (
            f"'{obj_type}' found at '{found_location}'. "
            f"Pick position from the list: '{pick_pos}'. "
            f"Navigating there to pick it up."
        ),
        (
            f"Spotted '{obj_type}' at '{found_location}'. "
            f"The corresponding pick position is '{pick_pos}'. "
            f"Moving to acquire it."
        ),
    ])


def search_all_and_pick_close_gripper(pick_pos: str) -> str:
    """Reasoning before closing the gripper after a global search pick."""
    return random.choice([
        f"I am aligned at '{pick_pos}'. Closing gripper to acquire the object.",
        f"At '{pick_pos}'. Gripping the object now.",
        f"Positioned at '{pick_pos}'. Closing gripper.",
        f"In position at '{pick_pos}'. Engaging gripper to pick up.",
        f"Reached '{pick_pos}'. Closing the gripper.",
    ])


# --- observe_and_place --------------------------------------------------------


def observe_and_place_init(obj_type: str, location_group_name: str) -> str:
    """Initial status check reasoning for placement."""
    return random.choice([
        (
            f"I have been asked to place '{obj_type}' into '{location_group_name}'. "
            f"First, checking gripper state to confirm I am holding the object."
        ),
        (
            f"Task: place '{obj_type}' at '{location_group_name}'. "
            f"Let me verify that I'm holding the right object."
        ),
        (
            f"Need to place '{obj_type}' into '{location_group_name}'. "
            f"Checking gripper status first."
        ),
        (
            f"I must place '{obj_type}' at '{location_group_name}'. "
            f"Starting with a gripper state check."
        ),
        (
            f"Placing '{obj_type}' at '{location_group_name}'. "
            f"Let me confirm I'm holding it by checking status."
        ),
    ])


def observe_and_place_gripper_ready(obj_type: str) -> str:
    """Reasoning after confirming the gripper holds the correct object."""
    return random.choice([
        f"Gripper is holding '{obj_type}' as expected. Now I need to load available positions.",
        f"Confirmed: holding '{obj_type}'. Loading positions next.",
        f"Good, I have '{obj_type}' in the gripper. Fetching the position list.",
        f"Holding '{obj_type}' - correct. Let me load the available positions.",
        f"Gripper holds '{obj_type}'. Proceeding to get the positions.",
    ])


def observe_and_place_first_move(
    object_locations: List[str],
    observe_positions: List[str],
    obs_pos: str,
) -> str:
    """First occupancy-scan move - full plan."""
    return random.choice([
        (
            f"From the positions list, I found matching placement keys for targets: {object_locations}. "
            f"To check if these slots are empty, I must scan them. "
            f"I have identified the following suitable vantage points from the position list: {observe_positions}. "
            f"I will visit them in sequence. Moving to '{obs_pos}'."
        ),
        (
            f"Position list shows placement locations: {object_locations}. "
            f"I need to verify which are empty. "
            f"Observation points from the list: {observe_positions}. "
            f"Starting scan from '{obs_pos}'."
        ),
        (
            f"From the positions list, target slots are {object_locations}. "
            f"Vantage points to check occupancy: {observe_positions}. "
            f"Going to '{obs_pos}' first."
        ),
        (
            f"Identified placement locations from position list: {object_locations}. "
            f"I'll scan from {observe_positions} to find empty slots. "
            f"Heading to '{obs_pos}'."
        ),
        (
            f"The positions list reveals targets: {object_locations}. "
            f"To check availability, I need to scan from {observe_positions}. "
            f"Moving to '{obs_pos}' to begin."
        ),
    ])


def observe_and_place_subsequent_move(
    inspected_positions: List[str],
    obs_pos: str,
    occupied_so_far: List[str] = None,
    remaining_locations: List[str] = None,
) -> str:
    """Subsequent occupancy-scan move - progress report with memory."""
    parts = [random.choice([
        f"I have completed the scan from {inspected_positions}.",
        f"Finished scanning from {inspected_positions}.",
        f"Checked from {inspected_positions}.",
        f"Done with {inspected_positions}.",
        f"Scanned from {inspected_positions}.",
    ])]
    if occupied_so_far:
        parts.append(random.choice([
            f"Occupied so far: {occupied_so_far}.",
            f"Found occupied: {occupied_so_far}.",
            f"These locations are taken: {occupied_so_far}.",
            f"Already occupied: {occupied_so_far}.",
            f"Occupied locations detected: {occupied_so_far}.",
        ]))
    if remaining_locations:
        parts.append(random.choice([
            f"Still need to check: {remaining_locations}.",
            f"Remaining to inspect: {remaining_locations}.",
            f"Left to scan: {remaining_locations}.",
            f"Not yet checked: {remaining_locations}.",
            f"Unchecked: {remaining_locations}.",
        ]))
    parts.append(random.choice([
        f"Proceeding to the next planned vantage point: '{obs_pos}'.",
        f"Moving to '{obs_pos}'.",
        f"Heading to '{obs_pos}' next.",
        f"Continuing to '{obs_pos}'.",
        f"Next observation point: '{obs_pos}'. Going there.",
    ]))
    return " ".join(parts)


def observe_and_place_scan(
    obs_pos: str,
    object_locations: List[str],
) -> str:
    """Scan reasoning during occupancy check."""
    return random.choice([
        f"I am at '{obs_pos}'. Scanning the view to check if objects already exist at {object_locations}.",
        f"At '{obs_pos}'. Checking occupancy of {object_locations}.",
        f"Positioned at '{obs_pos}'. Scanning {object_locations} for existing objects.",
        f"Now at '{obs_pos}'. Looking at {object_locations} to see which are occupied.",
        f"At '{obs_pos}'. Verifying whether {object_locations} are empty or taken.",
    ])


def observe_and_place_decide(
    object_locations: List[str],
    occupied_locations: List[str],
    empty_locations: List[str],
    target_location: str,
    place_pos: str,
) -> str:
    """Reasoning for the placement decision after scanning."""
    return random.choice([
        (
            f"Analysis: {object_locations} minus Occupied {occupied_locations} "
            f"leaves Empty {empty_locations}. "
            f"Decision: Place at '{target_location}'. "
            f"I will move to '{place_pos}' to perform the action."
        ),
        (
            f"Scan results: occupied = {occupied_locations}, "
            f"empty = {empty_locations} (out of {object_locations}). "
            f"Placing at '{target_location}' via position '{place_pos}'."
        ),
        (
            f"Out of {object_locations}, {occupied_locations} are occupied and "
            f"{empty_locations} are free. "
            f"Choosing '{target_location}'. Moving to '{place_pos}'."
        ),
        (
            f"Available slots: {empty_locations} (occupied: {occupied_locations}). "
            f"I'll place at '{target_location}'. "
            f"Heading to '{place_pos}'."
        ),
        (
            f"Locations {occupied_locations} are taken. "
            f"Empty options: {empty_locations}. "
            f"Selected '{target_location}'. Going to '{place_pos}'."
        ),
    ])


def observe_and_place_open_gripper() -> str:
    """Reasoning before opening gripper during placement."""
    return random.choice([
        "Opening gripper.",
        "Releasing the object. Opening gripper.",
        "Gripper open - placing the object.",
        "Opening the gripper to release.",
        "Letting go. Opening gripper now.",
    ])


# --- status_only ---------------------------------------------------------------


def status_only_check() -> str:
    """Reasoning for the single get_status call."""
    return random.choice([
        "Checking current robot status.",
        "Let me check my current state.",
        "Querying robot status.",
        "Checking where I am and what I'm holding.",
        "Running a status check.",
    ])


# --- navigate_to ---------------------------------------------------------------


def navigate_to_check_position() -> str:
    """Reasoning for checking current position."""
    return random.choice([
        "Checking current position.",
        "Let me see where I am right now.",
        "Querying my current position.",
        "Need to know my starting position first.",
        "Checking where I am currently positioned.",
    ])


def navigate_to_load_positions() -> str:
    """Reasoning for loading available positions."""
    return random.choice([
        "Loading available positions.",
        "Fetching the positions list.",
        "Getting the list of available positions.",
        "Loading positions to plan my route.",
        "Retrieving the available positions.",
    ])


def navigate_to_pick_position(
    x: str, y: str, pick_pos: str,
) -> str:
    """Reasoning for navigating to a pick position (4.5)."""
    return random.choice([
        (
            f"User located '{x}' at '{y}'. "
            f"Scanning positions for pick position... Found '{pick_pos}'. Moving there."
        ),
        (
            f"'{x}' is known to be at '{y}'. "
            f"From the position list, pick position is '{pick_pos}'. Heading there."
        ),
        (
            f"The user confirmed '{x}' at '{y}'. "
            f"Pick position from the list: '{pick_pos}'. Going there now."
        ),
        (
            f"'{x}' has been located at '{y}'. "
            f"Looking up the pick position... '{pick_pos}'. Navigating there."
        ),
        (
            f"Since '{x}' is at '{y}', I need pick position '{pick_pos}'. "
            f"Moving to that position."
        ),
    ])


def navigate_to_merged_first_obs(
    y: str, z: str, merged_obs: List[str], obs_pos: str,
) -> str:
    """First observation-point move for merged Y+Z visit (4.4)."""
    return random.choice([
        (
            f"Need to visit observation points covering both '{y}' and '{z}'. "
            f"From the positions list, I can cover both with: {merged_obs}. "
            f"Moving to '{obs_pos}' first."
        ),
        (
            f"I have to observe both '{y}' and '{z}'. "
            f"From the positions list, the observation points that cover both are {merged_obs}. "
            f"Going to '{obs_pos}'."
        ),
        (
            f"Plan: observe '{y}' and '{z}' together. "
            f"From the positions list, viewpoints covering both: {merged_obs}. "
            f"Heading to '{obs_pos}' first."
        ),
        (
            f"Two locations to observe: '{y}' and '{z}'. "
            f"The positions list shows I need these observation points: {merged_obs}. "
            f"Starting at '{obs_pos}'."
        ),
        (
            f"Visiting observation points for '{y}' and '{z}'. "
            f"From the positions list: {merged_obs} cover both groups. "
            f"Moving to '{obs_pos}'."
        ),
    ])


def navigate_to_merged_subsequent_obs(
    inspected: List[str], y: str, z: str, obs_pos: str,
) -> str:
    """Subsequent observation-point move for merged Y+Z visit (4.4)."""
    return random.choice([
        f"Visited {inspected} for '{y}' and '{z}'. Moving to next observation point: '{obs_pos}'.",
        f"Already checked {inspected} covering '{y}' and '{z}'. Continuing to '{obs_pos}'.",
        f"Covered {inspected} for '{y}' and '{z}'. Next viewpoint: '{obs_pos}'.",
        f"Inspected from {inspected} for both groups. Heading to '{obs_pos}'.",
        f"Done with {inspected}. Proceeding to '{obs_pos}' to cover more of '{y}' and '{z}'.",
    ])


def navigate_to_observe_first(
    y: str, obs_positions: List[str], obs_pos: str,
) -> str:
    """First observation move for Y-only navigation (4.2)."""
    return random.choice([
        (
            f"Need to observe '{y}'. "
            f"From the positions list, observation positions: {obs_positions}. "
            f"Moving to '{obs_pos}'."
        ),
        (
            f"I need to go to the observation point for '{y}'. "
            f"The positions list shows: {obs_positions}. "
            f"Heading to '{obs_pos}'."
        ),
        (
            f"Task: observe '{y}'. "
            f"Observation positions from the list: {obs_positions}. "
            f"Going to '{obs_pos}' first."
        ),
        (
            f"Navigating to observe '{y}'. "
            f"From the positions list, viewpoints: {obs_positions}. "
            f"Starting at '{obs_pos}'."
        ),
        (
            f"I want to observe '{y}'. "
            f"From the positions list, the observation points are {obs_positions}. "
            f"Moving to '{obs_pos}'."
        ),
    ])


def navigate_to_observe_subsequent(
    inspected: List[str], obs_pos: str,
) -> str:
    """Subsequent observation move for Y-only navigation (4.2)."""
    return random.choice([
        f"Visited {inspected}. Moving to next observation point: '{obs_pos}'.",
        f"Already at {inspected}. Continuing to '{obs_pos}'.",
        f"Checked {inspected}. Next viewpoint: '{obs_pos}'.",
        f"Done with {inspected}. Heading to '{obs_pos}'.",
        f"Covered {inspected}. Proceeding to '{obs_pos}'.",
    ])


def navigate_to_home() -> str:
    """Reasoning for moving to home position (4.1)."""
    return random.choice([
        "Moving to home position.",
        "Navigating to the home position.",
        "Going home.",
        "Returning to the home position.",
        "Heading to home.",
    ])


# --- observe_and_report -------------------------------------------------------


def observe_and_report_check_status() -> str:
    """Reasoning for the initial status check."""
    return random.choice([
        "Checking status before observing.",
        "Let me check my state before I start observing.",
        "Starting with a status check.",
        "Verifying current state first.",
        "Checking my position and gripper before observing.",
    ])


def observe_and_report_load_positions() -> str:
    """Reasoning for loading positions."""
    return random.choice([
        "Loading available positions.",
        "Fetching the positions list.",
        "Getting the list of available positions.",
        "Loading positions to find observation points.",
        "Retrieving available positions.",
    ])


# --- observe_and_report_all ---------------------------------------------------


def observe_and_report_all_check_status() -> str:
    """Reasoning for the initial status check in full-inventory scan."""
    return random.choice([
        "Checking status before inventory scan.",
        "Starting with a status check before the full scan.",
        "Let me verify my state before scanning all locations.",
        "Checking current status before beginning the inventory.",
        "Status check first, then I'll scan everything.",
    ])


def observe_and_report_all_load_positions() -> str:
    """Reasoning for loading positions in full-inventory scan."""
    return random.choice([
        "Loading available positions.",
        "Fetching positions for the inventory scan.",
        "Getting the position list to plan the scan.",
        "Loading positions to identify observation points.",
        "Retrieving positions for the full scan.",
    ])


def observe_and_report_all_plan(
    y: str,
    y_locs: List[str],
    total: int,
) -> str:
    """Reasoning about the slot structure before scanning (used for 5.6 etc.)."""
    return random.choice([
        (
            f"The user asked about '{y}'. "
            f"It has {total} slots: {y_locs}. "
            f"I need to scan all of them to determine occupancy."
        ),
        (
            f"'{y}' contains {total} locations: {y_locs}. "
            f"I must check each one to answer the user's question."
        ),
        (
            f"Examining '{y}'. It consists of {total} slots: {y_locs}. "
            f"I'll scan them all to get the full picture."
        ),
        (
            f"The user wants information about '{y}', which has {total} slots: {y_locs}. "
            f"Scanning all of them."
        ),
        (
            f"'{y}' has {total} locations to check: {y_locs}. "
            f"I need to visit observation points that cover all of them."
        ),
    ])


# --- observe_and_pick_any -----------------------------------------------------


def observe_and_pick_any_check_gripper() -> str:
    """Reasoning for the initial gripper check."""
    return random.choice([
        "Checking gripper state before picking.",
        "Let me verify the gripper is free before I try to pick.",
        "Starting with a gripper check.",
        "Need to confirm the gripper is open. Checking status.",
        "Checking my current state before picking.",
    ])


def observe_and_pick_any_load_positions() -> str:
    """Reasoning after gripper confirmed open."""
    return random.choice([
        "Gripper is open. Loading positions.",
        "Good, gripper is free. Fetching positions.",
        "Gripper confirmed open. Loading the position list.",
        "Gripper is ready. Getting available positions.",
        "Gripper open. Let me load the positions.",
    ])


# --- observe_and_pick_return_origin -------------------------------------------


def pick_return_origin_check_status() -> str:
    """Reasoning for the initial status check (remember origin)."""
    return random.choice([
        (
            "Checking current position and gripper state. I need to remember "
            "my starting position so I can return here after completing the pick."
        ),
        (
            "Let me check where I am and my gripper state. "
            "I'll need to come back to this position later."
        ),
        (
            "Status check - I need to note my current position as the return point "
            "and verify the gripper is ready."
        ),
        (
            "Checking status. Important: I must record my starting position "
            "so I can navigate back after picking."
        ),
        (
            "Verifying state. I need to memorize my current position "
            "for the return trip after the pick operation."
        ),
    ])


def pick_return_origin_load_positions(origin: str) -> str:
    """Reasoning after confirming gripper and recording origin."""
    return random.choice([
        (
            f"Gripper is open and ready. My current position is '{origin}'. "
            f"I will return here after the pick operation. Now loading available positions."
        ),
        (
            f"Good, gripper is open. Noted my origin: '{origin}'. "
            f"Loading positions to plan the pick."
        ),
        (
            f"Gripper is free. Starting position recorded as '{origin}'. "
            f"Fetching the position list."
        ),
        (
            f"Gripper confirmed open. Origin saved: '{origin}'. "
            f"Getting available positions."
        ),
        (
            f"Ready to go - gripper is open, origin is '{origin}'. "
            f"Loading the positions list."
        ),
    ])


def pick_return_origin_return_success(obj: str, origin: str) -> str:
    """Reasoning for returning to origin after successful pick."""
    return random.choice([
        f"Picked up '{obj}'. Returning to origin '{origin}'.",
        f"Got '{obj}'. Heading back to '{origin}'.",
        f"Successfully picked '{obj}'. Now going back to '{origin}'.",
        f"'{obj}' acquired. Navigating back to origin '{origin}'.",
        f"Have '{obj}'. Time to return to '{origin}'.",
    ])


def pick_return_origin_return_empty(y: str, origin: str) -> str:
    """Reasoning for returning to origin when source is empty."""
    return random.choice([
        f"'{y}' is empty. Returning to '{origin}'.",
        f"Nothing found at '{y}'. Heading back to '{origin}'.",
        f"'{y}' has no objects. Going back to '{origin}'.",
        f"Source '{y}' is empty. Returning to origin '{origin}'.",
        f"No objects at '{y}'. Navigating back to '{origin}'.",
    ])


def pick_return_origin_return_wrong_type(
    found_type: str, y: str, x: str, origin: str, found_items: str = "",
) -> str:
    """Reasoning for returning to origin when wrong type found."""
    detail = found_items if found_items else f"'{found_type}'"
    return random.choice([
        f"Found {detail} at '{y}', not '{x}'. Returning to '{origin}'.",
        f"'{y}' has {detail} instead of '{x}'. Going back to '{origin}'.",
        f"Wrong type: {detail} at '{y}' (wanted '{x}'). Heading back to '{origin}'.",
        f"{detail} is at '{y}', but I need '{x}'. Returning to '{origin}'.",
        f"Expected '{x}' at '{y}' but found {detail}. Going to '{origin}'.",
    ])


def pick_return_origin_return_any_success(obj: str, origin: str) -> str:
    """Reasoning for returning to origin after picking any object."""
    return random.choice([
        f"Picked up '{obj}'. Returning to '{origin}'.",
        f"Got '{obj}'. Heading back to '{origin}'.",
        f"Successfully grabbed '{obj}'. Going back to '{origin}'.",
        f"'{obj}' picked up. Navigating back to '{origin}'.",
        f"Acquired '{obj}'. Time to return to '{origin}'.",
    ])


def pick_return_origin_return_any_empty(y: str, origin: str) -> str:
    """Reasoning for returning to origin when no objects at Y."""
    return random.choice([
        f"'{y}' is empty. Returning to '{origin}'.",
        f"Nothing at '{y}'. Going back to '{origin}'.",
        f"'{y}' has no objects. Heading back to '{origin}'.",
        f"No objects found at '{y}'. Returning to origin '{origin}'.",
        f"'{y}' is clear - nothing to pick. Going to '{origin}'.",
    ])


# --- search_all_and_place -----------------------------------------------------


def search_all_and_place_check_gripper(x: str) -> str:
    """Reasoning for the initial gripper check."""
    return random.choice([
        f"Need to place '{x}'. Checking gripper state.",
        f"Task: place '{x}'. Let me verify I'm holding it.",
        f"I should place '{x}'. Checking my gripper first.",
        f"Going to place '{x}'. Starting with a gripper check.",
        f"Placing '{x}' - let me confirm I have it in my gripper.",
    ])


def search_all_and_place_load_positions(x: str) -> str:
    """Reasoning after confirming gripper holds correct object."""
    return random.choice([
        f"Holding '{x}'. Loading positions.",
        f"Confirmed: I have '{x}'. Fetching positions.",
        f"'{x}' is in the gripper. Getting the position list.",
        f"Gripper holds '{x}'. Loading available positions.",
        f"Good, holding '{x}'. Let me load the positions.",
    ])


def search_all_place_context_generic(x: str) -> str:
    """Scenario-specific context: place anywhere."""
    return random.choice([
        (
            f"I need to find any empty location in the environment to place '{x}'. "
            f"I will scan observation points until I find an empty spot."
        ),
        (
            f"Task: place '{x}' at any available location. "
            f"I'll search the environment for an empty slot."
        ),
        (
            f"I have to put '{x}' down somewhere. "
            f"Scanning the environment to find a free location."
        ),
        (
            f"Need to find an open spot for '{x}'. "
            f"I'll check observation points one by one."
        ),
        (
            f"Looking for any empty location to place '{x}'. "
            f"Will scan from observation points until I find one."
        ),
    ])


def search_all_place_context_prefer(x: str, y: str) -> str:
    """Scenario-specific context: place with preference for Y."""
    return random.choice([
        (
            f"I need to place '{x}' with a preference for '{y}'. "
            f"I should first check if '{y}' has an empty slot. "
            f"If '{y}' is full, I will look for any other empty location."
        ),
        (
            f"Task: place '{x}', preferably at '{y}'. "
            f"If '{y}' is occupied, I'll find another spot."
        ),
        (
            f"I want to put '{x}' at '{y}' if possible. "
            f"Otherwise, any empty location will do."
        ),
        (
            f"Preferred placement for '{x}' is '{y}'. "
            f"I'll check there first, then look elsewhere if needed."
        ),
        (
            f"'{y}' is the preferred location for '{x}'. "
            f"If it's not available, I'll scan for alternatives."
        ),
    ])


def search_all_place_context_avoid(x: str, y: str) -> str:
    """Scenario-specific context: place but not at Y."""
    return random.choice([
        (
            f"I need to place '{x}' somewhere, but NOT at '{y}'. "
            f"I will scan the environment for an empty location outside of '{y}'."
        ),
        (
            f"Task: place '{x}' anywhere except '{y}'. "
            f"Searching for an available spot that's not at '{y}'."
        ),
        (
            f"I have to put '{x}' down, but '{y}' is off-limits. "
            f"Looking for other empty locations."
        ),
        (
            f"Placing '{x}' - any location except '{y}'. "
            f"I'll scan for empty spots outside '{y}'."
        ),
        (
            f"Need an empty spot for '{x}' that isn't '{y}'. "
            f"Scanning the environment for alternatives."
        ),
    ])


def search_all_and_place_first_scan(
    all_observe: List[str],
    obs_pos: str,
    visible_locations: List[str] = None,
) -> str:
    """First observation move in global scan for empty spot."""
    base = random.choice([
        (
            f"From the positions list, scanning all observation points: {all_observe}. "
            f"Moving to '{obs_pos}' to find an empty location."
        ),
        (
            f"Observation points from the position list: {all_observe}. "
            f"Starting the scan at '{obs_pos}'."
        ),
        (
            f"The position list gives these observation points: {all_observe}. "
            f"I'll scan from each. Going to '{obs_pos}' first."
        ),
        (
            f"From the positions list, vantage points are {all_observe}. "
            f"Heading to '{obs_pos}' to begin looking for empty slots."
        ),
        (
            f"Available observation points from the list: {all_observe}. "
            f"Navigating to '{obs_pos}' to start scanning."
        ),
    ])
    if visible_locations:
        base += random.choice([
            f" From there I can see {visible_locations}.",
            f" This covers {visible_locations}.",
            f" Visible from there: {visible_locations}.",
            f" Coverage: {visible_locations}.",
            f" That position shows {visible_locations}.",
        ])
    return base


def search_all_and_place_subsequent_scan(
    inspected: List[str],
    obs_pos: str,
    findings: Dict[str, str] = None,
    visible_locations: List[str] = None,
) -> str:
    """Subsequent observation move in global scan with memory."""
    parts = [random.choice([
        f"Scanned from {inspected}.",
        f"Checked {inspected}.",
        f"Visited {inspected}.",
        f"Already scanned from {inspected}.",
        f"Completed scanning at {inspected}.",
    ])]
    if findings:
        occupied = [f"'{loc}': '{obj}'" for loc, obj in findings.items()]
        parts.append(random.choice([
            f"Occupied so far: {', '.join(occupied)}.",
            f"Found occupied: {', '.join(occupied)}.",
            f"Locations taken: {', '.join(occupied)}.",
            f"Occupied positions: {', '.join(occupied)}.",
            f"Objects found: {', '.join(occupied)}.",
        ]))
    parts.append(random.choice([
        f"No valid empty location found yet. Moving to '{obs_pos}'.",
        f"Still no empty spot. Continuing to '{obs_pos}'.",
        f"Haven't found an empty location yet. Heading to '{obs_pos}'.",
        f"No free slots so far. Proceeding to '{obs_pos}'.",
        f"Empty spot not found yet. Going to '{obs_pos}'.",
    ]))
    if visible_locations:
        parts.append(random.choice([
            f"From there I can see {visible_locations}.",
            f"Coverage: {visible_locations}.",
            f"Visible: {visible_locations}.",
            f"That position covers {visible_locations}.",
            f"It overlooks {visible_locations}.",
        ]))
    return " ".join(parts)


def search_all_and_place_locate(
    obs_pos: str,
    visible_locations: List[str] = None,
) -> str:
    """Scan reasoning at a vantage point during global place search."""
    if visible_locations:
        return random.choice([
            f"At '{obs_pos}'. This position covers {visible_locations}. Scanning for occupied locations.",
            f"At '{obs_pos}', covering {visible_locations}. Checking which are occupied.",
            f"Positioned at '{obs_pos}'. Visible: {visible_locations}. Scanning occupancy.",
            f"Now at '{obs_pos}'. I can see {visible_locations}. Checking for objects.",
            f"At vantage point '{obs_pos}'. Coverage: {visible_locations}. Running scan.",
        ])
    return random.choice([
        f"At '{obs_pos}'. Scanning for occupied locations.",
        f"At '{obs_pos}'. Checking occupancy.",
        f"Positioned at '{obs_pos}'. Scanning area.",
        f"Now at '{obs_pos}'. Looking for objects.",
        f"At '{obs_pos}'. Running occupancy scan.",
    ])


# --- observe_and_place_with_fallback ------------------------------------------


def place_with_fallback_check_gripper(x: str) -> str:
    """Reasoning for the initial gripper check."""
    return random.choice([
        f"Need to place '{x}'. Checking gripper.",
        f"Task: place '{x}'. Verifying gripper state.",
        f"Going to place '{x}'. Let me check the gripper first.",
        f"Placing '{x}' - checking that I'm holding it.",
        f"I should place '{x}'. Starting with a gripper check.",
    ])


def place_with_fallback_load_positions(x: str) -> str:
    """Reasoning after confirming gripper holds correct object."""
    return random.choice([
        f"Holding '{x}'. Loading positions.",
        f"Confirmed: holding '{x}'. Getting the position list.",
        f"'{x}' in gripper. Fetching positions.",
        f"Good, I have '{x}'. Loading available positions.",
        f"Gripper holds '{x}'. Let me load positions.",
    ])


def place_fallback_context_yz(x: str, y: str, z: str) -> str:
    """Scenario-specific context: try Y, fall back to Z."""
    return random.choice([
        (
            f"I need to place '{x}' at '{y}'. "
            f"If '{y}' is occupied, I should try '{z}' as a fallback."
        ),
        (
            f"Task: place '{x}' at '{y}', with '{z}' as backup if '{y}' is full."
        ),
        (
            f"I want to put '{x}' at '{y}'. "
            f"If that's not possible, '{z}' is the alternative."
        ),
        (
            f"Primary target for '{x}' is '{y}'. "
            f"Fallback: '{z}' if '{y}' has no room."
        ),
        (
            f"Plan: place '{x}' at '{y}'. "
            f"If '{y}' is occupied, try '{z}' instead."
        ),
    ])


def place_fallback_context_strict(x: str, y: str) -> str:
    """Scenario-specific context: only Y, nowhere else."""
    return random.choice([
        (
            f"I need to place '{x}' at '{y}' only. "
            f"If '{y}' is occupied, I must not try elsewhere."
        ),
        (
            f"Task: place '{x}' strictly at '{y}'. "
            f"No alternative locations allowed."
        ),
        (
            f"I can only place '{x}' at '{y}'. "
            f"If it's full, I have to report failure."
        ),
        (
            f"'{y}' is the only allowed location for '{x}'. "
            f"No fallback options."
        ),
        (
            f"Strict placement: '{x}' goes at '{y}' or nowhere."
        ),
    ])


def place_fallback_context_conditional(
    x: str, y: str, z: str, w: str,
) -> str:
    """Scenario-specific context: place at Y unless W is there."""
    return random.choice([
        (
            f"I need to place '{x}' at '{y}'. However, if '{y}' contains "
            f"a '{w}', I should redirect and place at '{z}' instead. "
            f"I need to check what is at '{y}' first."
        ),
        (
            f"Task: place '{x}' at '{y}', but if there's a '{w}' at '{y}', "
            f"go to '{z}' instead. I must inspect '{y}' first."
        ),
        (
            f"Plan: put '{x}' at '{y}' unless '{w}' is present there. "
            f"In that case, use '{z}'. Checking '{y}' first."
        ),
        (
            f"Conditional placement: '{x}' goes at '{y}' if '{w}' isn't there. "
            f"If '{w}' is at '{y}', redirect to '{z}'. "
            f"Need to scan '{y}' first."
        ),
        (
            f"I want to place '{x}' at '{y}'. But if I find '{w}' at '{y}', "
            f"the fallback is '{z}'. Let me check '{y}'."
        ),
    ])


def place_fallback_non_w_found(
    y: str,
    w: str,
    found_type: str,
    found_loc: str,
    y_empty: List[str],
) -> str:
    """Reasoning when Y has an object that is not W."""
    if y_empty:
        return random.choice([
            (
                f"I found '{found_type}' at '{found_loc}' in '{y}'. "
                f"It is not '{w}', so the redirect condition is not triggered. "
                f"'{y}' still has empty slots: {y_empty}. I can place here."
            ),
            (
                f"'{found_loc}' has '{found_type}', not '{w}'. No redirect needed. "
                f"Empty slots at '{y}': {y_empty}. Proceeding to place."
            ),
            (
                f"Found '{found_type}' at '{found_loc}' - not '{w}', so no redirect. "
                f"'{y}' has room: {y_empty}. I'll place here."
            ),
            (
                f"'{found_type}' at '{found_loc}' is not the forbidden '{w}'. "
                f"Available slots in '{y}': {y_empty}. Placing here."
            ),
            (
                f"Detected '{found_type}' at '{found_loc}', which is not '{w}'. "
                f"Redirect not triggered. Free spots at '{y}': {y_empty}."
            ),
        ])
    return random.choice([
        (
            f"I found '{found_type}' at '{found_loc}' in '{y}'. "
            f"It is not '{w}', so the redirect condition is not triggered. "
            f"However, '{y}' has no empty slots remaining."
        ),
        (
            f"'{found_loc}' has '{found_type}', not '{w}'. No redirect. "
            f"But '{y}' is fully occupied - no room to place."
        ),
        (
            f"Found '{found_type}' at '{found_loc}' - not '{w}'. "
            f"No redirect needed, but '{y}' has no free slots."
        ),
        (
            f"'{found_type}' is at '{found_loc}', not '{w}'. No redirect triggered. "
            f"Unfortunately '{y}' is full."
        ),
        (
            f"Detected '{found_type}' at '{found_loc}', not '{w}'. "
            f"Redirect condition not met, but '{y}' has no available space."
        ),
    ])


def place_fallback_y_empty_no_w(
    y: str, w: str, y_empty: List[str],
) -> str:
    """Reasoning when Y is completely empty (no W concern)."""
    return random.choice([
        (
            f"'{y}' is empty. No '{w}' found, so the redirect condition "
            f"is not triggered. Available slots: {y_empty}. I can place here."
        ),
        (
            f"'{y}' has nothing in it - no '{w}'. "
            f"Free slots: {y_empty}. Placing here."
        ),
        (
            f"No objects at '{y}', so definitely no '{w}'. "
            f"No redirect needed. Available: {y_empty}."
        ),
        (
            f"'{y}' is clear - no '{w}' present. "
            f"Open slots: {y_empty}. I can place the object here."
        ),
        (
            f"Scanned '{y}': empty. '{w}' not found, redirect not triggered. "
            f"Slots available: {y_empty}."
        ),
    ])


# --- pick_and_place ------------------------------------------------------------


def pick_and_place_check_gripper() -> str:
    """Reasoning for the initial gripper check."""
    return random.choice([
        "Checking gripper state before pick-and-place.",
        "Need to verify the gripper is open before starting the pick-and-place.",
        "Let me check my gripper state for the pick-and-place operation.",
        "Starting pick-and-place. Checking gripper first.",
        "Gripper check before the pick-and-place task.",
    ])


def pick_and_place_load_positions() -> str:
    """Reasoning after gripper confirmed open."""
    return random.choice([
        "Gripper open. Loading positions.",
        "Good, gripper is free. Fetching the position list.",
        "Gripper confirmed open. Getting available positions.",
        "Gripper is ready. Loading positions.",
        "Gripper is open. Let me load the positions.",
    ])


def pick_and_place_context(
    x: str, y: str, z: str,
) -> str:
    """Scenario-specific context for pick-and-place."""
    if x:
        return random.choice([
            (
                f"I need to pick up '{x}' from '{y}' and place it at '{z}'. "
                f"This is a two-phase operation: first pick, then place."
            ),
            (
                f"Task: move '{x}' from '{y}' to '{z}'. "
                f"Phase 1: pick from '{y}'. Phase 2: place at '{z}'."
            ),
            (
                f"I have to transfer '{x}' from '{y}' to '{z}'. "
                f"Starting with the pick phase."
            ),
            (
                f"The goal is to move '{x}': pick it from '{y}', then place at '{z}'."
            ),
            (
                f"Moving '{x}' from '{y}' to '{z}'. "
                f"First I'll pick it up, then find a spot at '{z}'."
            ),
        ])
    return random.choice([
        (
            f"I need to pick whatever is at '{y}' and place it at '{z}'. "
            f"This is a two-phase operation: first pick, then place."
        ),
        (
            f"Task: grab whatever is at '{y}' and move it to '{z}'."
        ),
        (
            f"I have to take what's at '{y}' and put it at '{z}'. "
            f"Pick first, then place."
        ),
        (
            f"Moving the object from '{y}' to '{z}'. "
            f"Starting with the pick phase."
        ),
        (
            f"Plan: pick up from '{y}', then place at '{z}'."
        ),
    ])


def pick_and_place_transition(
    picked_type: str,
    picked_from: str,
    z: str,
) -> str:
    """Reasoning for the transition between pick and place phases."""
    return random.choice([
        (
            f"Successfully picked up '{picked_type}' from '{picked_from}'. "
            f"Now I need to check '{z}' for an empty placement location. "
            f"Moving to observation phase for '{z}'."
        ),
        (
            f"Got '{picked_type}' from '{picked_from}'. "
            f"Next step: find an empty spot at '{z}'. Heading to observe '{z}'."
        ),
        (
            f"Picked '{picked_type}' from '{picked_from}'. "
            f"Phase 2: place it at '{z}'. Need to scan '{z}' for availability."
        ),
        (
            f"'{picked_type}' picked from '{picked_from}'. "
            f"Now checking '{z}' for a free slot."
        ),
        (
            f"Pick phase complete: '{picked_type}' from '{picked_from}'. "
            f"Now scanning '{z}' to find an empty location for placement."
        ),
    ])


def pick_and_place_return_to_source(
    picked_type: str, z: str, y: str,
) -> str:
    """Reasoning for returning the object to the source when Z is full."""
    return random.choice([
        (
            f"All locations at '{z}' are occupied. I cannot place '{picked_type}' there. "
            f"As instructed, I will return '{picked_type}' to '{y}'."
        ),
        (
            f"'{z}' is fully occupied - no room for '{picked_type}'. "
            f"Returning it to '{y}' as instructed."
        ),
        (
            f"Cannot place '{picked_type}' at '{z}' - it's full. "
            f"Bringing '{picked_type}' back to '{y}'."
        ),
        (
            f"No empty slots at '{z}'. "
            f"I'll return '{picked_type}' to its source '{y}'."
        ),
        (
            f"'{z}' has no room. "
            f"Taking '{picked_type}' back to '{y}'."
        ),
    ])


def pick_and_place_return_open_gripper() -> str:
    """Reasoning for opening the gripper when returning the object."""
    return random.choice([
        "Opening gripper to return object to its original location.",
        "Releasing the object back at its source. Opening gripper.",
        "Putting it back. Opening gripper.",
        "Returning the object. Opening gripper to release.",
        "Opening gripper to drop the object back where it was.",
    ])


# --- PICK SCENARIO CONTEXT ---------------------------------------------------


def observe_and_pick_context(x: str, y: str) -> str:
    """Scenario context for observe_and_pick: find and pick X from Y."""
    return random.choice([
        f"The user asked me to find and pick up '{x}' from '{y}'.",
        f"Task: locate '{x}' at '{y}' and pick it up.",
        f"I need to find '{x}' at '{y}' and grab it.",
        f"The instruction is to pick up '{x}' from '{y}'.",
        f"Goal: retrieve '{x}' from '{y}'.",
    ])


def search_all_and_pick_context(x: str) -> str:
    """Scenario context for search_all_and_pick: find X anywhere."""
    return random.choice([
        f"The user asked me to find '{x}' in the environment.",
        f"Task: search the environment for '{x}' and pick it up.",
        f"I need to locate '{x}' somewhere and grab it.",
        f"The instruction is to find and pick up '{x}' - location unknown.",
        f"Goal: find '{x}' anywhere in the scene and pick it up.",
    ])


def observe_and_pick_any_context_xw(x: str, w: str, y: str) -> str:
    """Scenario context for pick X or W from Y."""
    return random.choice([
        (
            f"The user asked me to pick up a '{x}' or a '{w}' from '{y}', "
            f"whichever is there."
        ),
        (
            f"Task: grab either '{x}' or '{w}' from '{y}' - whatever I find."
        ),
        (
            f"I should pick up '{x}' or '{w}' from '{y}', "
            f"taking whichever is available."
        ),
        (
            f"The instruction is to get a '{x}' or a '{w}' from '{y}'."
        ),
        (
            f"Goal: pick up either '{x}' or '{w}' from '{y}'."
        ),
    ])


def observe_and_pick_any_context_unless_w(w: str, y: str) -> str:
    """Scenario context for pick unless W."""
    return random.choice([
        (
            f"The user asked me to pick up whatever is at '{y}', "
            f"as long as it is not a '{w}'."
        ),
        (
            f"Task: grab anything at '{y}' except '{w}'."
        ),
        (
            f"I should pick up the object at '{y}', "
            f"but only if it's not a '{w}'."
        ),
        (
            f"The instruction is to take whatever is at '{y}', "
            f"excluding '{w}'."
        ),
        (
            f"Goal: pick from '{y}', but avoid picking a '{w}'."
        ),
    ])


def observe_and_pick_any_context_y_else_z(y: str, z: str) -> str:
    """Scenario context for pick from Y else Z."""
    return random.choice([
        (
            f"The user asked me to pick from '{y}'. "
            f"If '{y}' is empty, try '{z}' instead."
        ),
        (
            f"Task: pick up from '{y}', with '{z}' as fallback if '{y}' is empty."
        ),
        (
            f"I should grab something from '{y}'. "
            f"If nothing is there, check '{z}'."
        ),
        (
            f"The instruction is to pick from '{y}' first. "
            f"If empty, try '{z}'."
        ),
        (
            f"Goal: get an object from '{y}'. Fallback: '{z}'."
        ),
    ])


def observe_and_pick_any_context_whatever(y: str) -> str:
    """Scenario context for pick whatever at Y."""
    return random.choice([
        f"The user asked me to pick up whatever is at '{y}'.",
        f"Task: grab whatever object is at '{y}'.",
        f"I should pick up the object at '{y}', whatever it is.",
        f"The instruction is to take whatever is at '{y}'.",
        f"Goal: pick up the item at '{y}'.",
    ])


def pick_return_origin_context(x: str, y: str) -> str:
    """Scenario context for pick and return to origin."""
    if x:
        return random.choice([
            (
                f"The user asked me to get '{x}' from '{y}' and "
                f"return to my starting position."
            ),
            (
                f"Task: retrieve '{x}' from '{y}', then come back to where I started."
            ),
            (
                f"I need to fetch '{x}' from '{y}' and return here afterward."
            ),
            (
                f"The instruction is to pick up '{x}' at '{y}' "
                f"and bring it back to my origin."
            ),
            (
                f"Goal: grab '{x}' from '{y}', then navigate back to my starting spot."
            ),
        ])
    return random.choice([
        (
            f"The user asked me to pick up whatever is at '{y}' "
            f"and bring it back."
        ),
        (
            f"Task: grab whatever object is at '{y}' and return to my starting position."
        ),
        (
            f"I need to pick up the object at '{y}' and come back here."
        ),
        (
            f"The instruction is to fetch whatever is at '{y}' and bring it back."
        ),
        (
            f"Goal: pick up the item at '{y}' and return to where I started."
        ),
    ])


# --- observe_conditional_pick ------------------------------------------------


def observe_conditional_pick_init(x: str, y: str) -> str:
    """Reasoning for initial status check in conditional pick."""
    return random.choice([
        (
            f"I need to check '{y}' for a '{x}'. If it's there, I'll pick it up. "
            f"If not, I'll report what I find. First, checking gripper state."
        ),
        (
            f"Task: inspect '{y}' for '{x}' - pick if found, otherwise report. "
            f"Let me check my current status."
        ),
        (
            f"The user wants me to look at '{y}' for a '{x}' and conditionally pick it. "
            f"Starting with a gripper check."
        ),
        (
            f"Conditional pick: check '{y}' for '{x}'. "
            f"Need to verify gripper is free before I start."
        ),
        (
            f"I'll check '{y}' for '{x}' and decide whether to pick or report. "
            f"Checking my state first."
        ),
    ])


def observe_conditional_pick_gripper_ready(x: str, y: str) -> str:
    """Reasoning after gripper confirmed open - load positions."""
    return random.choice([
        f"Gripper is open - I can pick if '{x}' is at '{y}'. Loading positions.",
        f"Good, gripper is free. Loading position list to find '{y}'.",
        f"Gripper confirmed open. Fetching positions to plan the check on '{y}'.",
        f"Gripper is ready. Let me load positions so I can navigate to '{y}'.",
        f"Gripper open. Now I need the position list to locate '{y}'.",
    ])


def observe_conditional_pick_context(x: str, y: str) -> str:
    """Scenario context for the conditional observation and pick."""
    return random.choice([
        (
            f"The user asked me to check '{y}' for a '{x}'. "
            f"If I find it, I should pick it up. Otherwise, just report what's there."
        ),
        (
            f"Task: look at '{y}'. If '{x}' is present, grab it. "
            f"If something else is there or it's empty, report back."
        ),
        (
            f"Conditional operation: inspect '{y}' for '{x}'. "
            f"Pick on match, report on mismatch or empty."
        ),
        (
            f"I need to observe '{y}' and check for '{x}'. "
            f"If found, pick it up. If not, tell the user what I see."
        ),
        (
            f"Goal: check '{y}' for '{x}' - pick if present, otherwise inform the user."
        ),
    ])


def observe_conditional_pick_found_x(x: str, found_loc: str) -> str:
    """Reasoning when X is found - deciding to pick."""
    return random.choice([
        (
            f"I found '{x}' at '{found_loc}'. "
            f"The condition is met - proceeding to pick it up."
        ),
        (
            f"'{x}' spotted at '{found_loc}'. "
            f"Condition satisfied. I'll pick it up now."
        ),
        (
            f"Target '{x}' is at '{found_loc}'. "
            f"Since the target is present, I will pick it up."
        ),
        (
            f"Located '{x}' at '{found_loc}'. "
            f"The user's condition is met, so I'm picking it up."
        ),
        (
            f"Found the '{x}' at '{found_loc}'. "
            f"Condition matched - moving to pick."
        ),
    ])


def observe_conditional_pick_found_different(x: str, found_type: str, y: str, found_items: str = "") -> str:
    """Reasoning when a different type is found - reporting instead of picking."""
    detail = found_items if found_items else f"'{found_type}'"
    return random.choice([
        (
            f"I found {detail} at '{y}', not '{x}'. "
            f"The condition is not met - I will report what I found instead."
        ),
        (
            f"'{y}' has {detail}, not the '{x}' I was looking for. "
            f"No pick. Reporting the finding."
        ),
        (
            f"At '{y}' I see {detail}, not '{x}'. "
            f"Condition not satisfied. I'll report back."
        ),
        (
            f"Found {detail} instead of '{x}' at '{y}'. "
            f"Not picking - just informing the user."
        ),
        (
            f"{detail} detected at '{y}' - not the target '{x}'. "
            f"Skipping pick and reporting."
        ),
    ])


def observe_conditional_pick_found_empty(x: str, y: str) -> str:
    """Reasoning when Y is empty - reporting empty."""
    return random.choice([
        (
            f"'{y}' is empty - no '{x}' or any other object found. "
            f"Nothing to pick. Reporting empty."
        ),
        (
            f"No objects at '{y}'. The '{x}' is not here. "
            f"Reporting that the location is empty."
        ),
        (
            f"'{y}' has nothing in it. Cannot pick '{x}' - it's not there. "
            f"Will inform the user."
        ),
        (
            f"Scanned '{y}' and found it empty. No '{x}' present. "
            f"Reporting the empty state."
        ),
        (
            f"'{y}' is clear - nothing found, including '{x}'. "
            f"Telling the user it's empty."
        ),
    ])


# --- compare_inventories -----------------------------------------------------


def compare_inventories_check_status() -> str:
    """Reasoning for initial status check."""
    return random.choice([
        "Starting a comparison scan across multiple locations. Checking status first.",
        "I need to compare inventories across locations. Let me check my state.",
        "Inventory comparison task. Checking current status.",
        "Beginning a multi-location comparison. Status check first.",
        "Comparing locations - let me verify my state before scanning.",
    ])


def compare_inventories_load_positions() -> str:
    """Reasoning for loading positions."""
    return random.choice([
        "Loading positions to plan the comparison scan.",
        "Fetching the position list for the inventory comparison.",
        "Getting available positions to visit all locations.",
        "Loading positions - I need to scan multiple location groups.",
        "Retrieving positions for the multi-location scan.",
    ])


def compare_inventories_plan(
    y: str, z: str,
    y_locs: List[str], z_locs: List[str],
) -> str:
    """Reasoning about the two-location merged scan plan."""
    return random.choice([
        (
            f"I need to compare '{y}' ({len(y_locs)} slots: {y_locs}) and "
            f"'{z}' ({len(z_locs)} slots: {z_locs}). "
            f"I'll scan all locations together and count objects per group."
        ),
        (
            f"Comparison plan: '{y}' has {len(y_locs)} locations, "
            f"'{z}' has {len(z_locs)} locations. "
            f"I can cover both groups in a single pass through their observation points."
        ),
        (
            f"Two groups to compare: '{y}' with {len(y_locs)} slots, "
            f"'{z}' with {len(z_locs)} slots. "
            f"I'll visit observation points that cover both and count objects."
        ),
        (
            f"Task: compare '{y}' ({y_locs}) and '{z}' ({z_locs}). "
            f"Will scan all locations in one pass to count objects per group."
        ),
        (
            f"I must scan '{y}' ({len(y_locs)} locations) and "
            f"'{z}' ({len(z_locs)} locations). "
            f"I'll visit observation points covering both groups together."
        ),
    ])


def compare_inventories_summary(
    y: str, y_count: int,
    z: str, z_count: int,
) -> str:
    """Reasoning for the final comparison result."""
    counts = {y: y_count, z: z_count}
    most = max(counts, key=counts.get)
    emptiest = min(counts, key=counts.get)
    return random.choice([
        (
            f"Results: '{y}' has {y_count} and '{z}' has {z_count} object(s). "
            f"'{most}' has the most and '{emptiest}' is the emptiest."
        ),
        (
            f"Comparison complete. '{y}': {y_count}, '{z}': {z_count}. "
            f"Most full: '{most}'. Emptiest: '{emptiest}'."
        ),
        (
            f"Final tally - '{y}': {y_count}, '{z}': {z_count}. "
            f"'{most}' leads with the most objects. '{emptiest}' has the fewest."
        ),
        (
            f"Scan results: '{y}' = {y_count}, '{z}' = {z_count}. "
            f"Winner: '{most}'. Emptiest: '{emptiest}'."
        ),
        (
            f"All scanned. '{y}': {y_count} object(s), '{z}': {z_count}. "
            f"'{most}' is the fullest, '{emptiest}' the emptiest."
        ),
    ])


# --- place_implicit_type -----------------------------------------------------


def place_implicit_type_init(y: str) -> str:
    """Reasoning for initial status check - no specific type to verify."""
    return random.choice([
        (
            f"The user wants me to place whatever I'm holding at '{y}'. "
            f"Checking what I have in the gripper."
        ),
        (
            f"Task: put down the held object at '{y}'. "
            f"Let me check what I'm holding."
        ),
        (
            f"I need to place my current object at '{y}'. "
            f"Checking gripper to see what I have."
        ),
        (
            f"Placing whatever is in the gripper at '{y}'. "
            f"Starting with a status check."
        ),
        (
            f"The user said to drop whatever I'm holding at '{y}'. "
            f"Let me verify I'm actually holding something."
        ),
    ])


def place_implicit_type_gripper_ready(held_type: str) -> str:
    """Reasoning after confirming gripper holds something (any type OK)."""
    return random.choice([
        f"I'm holding a '{held_type}'. Loading positions to find an empty slot.",
        f"Confirmed: holding '{held_type}'. Fetching positions.",
        f"Gripper has '{held_type}'. Getting the position list.",
        f"Good, I have '{held_type}' in the gripper. Loading available positions.",
        f"Holding '{held_type}'. Let me load positions to plan the placement.",
    ])


def place_implicit_type_context(held_type: str, y: str) -> str:
    """Scenario context for implicit placement."""
    return random.choice([
        (
            f"The user wants me to place whatever I have at '{y}'. "
            f"I'm holding '{held_type}'. I need to find an empty slot at '{y}'."
        ),
        (
            f"Task: put '{held_type}' (my current object) down at '{y}'. "
            f"Checking for available space."
        ),
        (
            f"Implicit placement - I have '{held_type}' and need to put it at '{y}'. "
            f"Scanning for empty locations."
        ),
        (
            f"I'm holding '{held_type}' and the user wants it placed at '{y}'. "
            f"Let me find an empty spot there."
        ),
        (
            f"Placing '{held_type}' at '{y}' as requested. "
            f"Need to verify there's room."
        ),
    ])


def place_implicit_type_decide(
    held_type: str,
    empty_locations: List[str],
    target_location: str,
    place_pos: str,
) -> str:
    """Reasoning for the placement decision."""
    return random.choice([
        (
            f"Found empty locations: {empty_locations}. "
            f"Placing '{held_type}' at '{target_location}'. "
            f"Moving to place position '{place_pos}'."
        ),
        (
            f"Available slots: {empty_locations}. "
            f"I'll put '{held_type}' at '{target_location}' via '{place_pos}'."
        ),
        (
            f"Empty spots: {empty_locations}. "
            f"Choosing '{target_location}' for '{held_type}'. "
            f"Heading to '{place_pos}'."
        ),
        (
            f"'{target_location}' is empty (options were {empty_locations}). "
            f"Moving to '{place_pos}' to release '{held_type}'."
        ),
        (
            f"Scan shows {empty_locations} are free. "
            f"Placing '{held_type}' at '{target_location}'. "
            f"Going to '{place_pos}'."
        ),
    ])
