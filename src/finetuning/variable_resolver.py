"""Variable resolution logic for scenario drafts."""

import random
from typing import Dict, List, Optional, Any

from tool_simulation_server.scene import SceneConfig, PositionType
from finetuning.models import VariableDefinition, VariableType, LocationMode


class VariableResolver:
    """Resolves scenario variables against a concrete scene configuration."""

    def __init__(self, scene_config: SceneConfig, random_seed: Optional[int] = None):
        self.config = scene_config
        if random_seed is not None:
            random.seed(random_seed)

    def resolve_all(self, variables: List[VariableDefinition]) -> Dict[str, str]:
        """
        Resolve all variables, respecting dependencies.
        Returns mapping of $VAR_NAME -> resolved_value
        """
        resolved: Dict[str, str] = {}

        # Sort variables by dependency (variables with constraints come after their dependencies)
        sorted_vars = self._sort_by_dependency(variables)

        for var_def in sorted_vars:
            value = self._resolve_single(var_def, resolved)
            resolved[var_def.name] = value

        return resolved

    def _resolve_single(
        self,
        var_def: VariableDefinition,
        already_resolved: Dict[str, str]
    ) -> str:
        """Resolve a single variable."""
        if var_def.type == VariableType.OBJECT_TYPE:
            return self._resolve_object_type(var_def, already_resolved)
        elif var_def.type == VariableType.LOCATION:
            return self._resolve_location(var_def, already_resolved)
        else:
            raise ValueError(f"Unknown variable type: {var_def.type}")

    def _get_location_exclusion_set(self, resolved_value: str) -> set:
        """Get full exclusion set for a location, including group members."""
        excluded = {resolved_value}
        if self.config.location_names:
            resolved_members: set = set()
            # If resolved to a group name, exclude all member locations
            if resolved_value in self.config.location_names:
                resolved_members = set(self.config.location_names[resolved_value])
                excluded.update(resolved_members)
            # If resolved to a specific location, exclude parent groups and siblings
            for group_name, members in self.config.location_names.items():
                if resolved_value in members:
                    excluded.add(group_name)
                    excluded.update(members)
                    resolved_members.update(members)
            # Exclude any other group that overlaps with the resolved members
            if resolved_members:
                for group_name, members in self.config.location_names.items():
                    if group_name not in excluded and set(members) & resolved_members:
                        excluded.add(group_name)
        return excluded

    def _resolve_object_type(
        self,
        var_def: VariableDefinition,
        resolved: Dict[str, str]
    ) -> str:
        """Resolve to a random object type from the scene."""
        candidates = list(self.config.object_types)

        # Apply must_differ_from constraint (single string or list of strings)
        if var_def.constraints and "must_differ_from" in var_def.constraints:
            ref = var_def.constraints["must_differ_from"]
            ref_vars = ref if isinstance(ref, list) else [ref]
            excluded_vals = {resolved[r] for r in ref_vars if r in resolved}
            candidates = [c for c in candidates if c not in excluded_vals]

        if not candidates:
            raise ValueError(f"No object types available after applying constraints for {var_def.name}")

        return random.choice(candidates)

    def _resolve_location(
        self,
        var_def: VariableDefinition,
        resolved: Dict[str, str]
    ) -> str:
        """Resolve to a location based on mode."""
        mode = var_def.mode

        # Get usable object locations (excluding ATTACHED, UNDEFINED)
        object_locations = [
            loc for loc in self.config.object_locations
            if loc not in ("ATTACHED", "UNDEFINED")
        ]

        # Get location names if available
        location_names = list(self.config.location_names.keys()) if self.config.location_names else []

        # Apply must_differ_from exclusion
        # OBJECT_LOCATION mode: simple exclusion (just the exact resolved value)
        #   — group-aware exclusion is too aggressive here because overlapping
        #     groups can exclude ALL locations in small scenes.
        # LOCATION_NAME / ANY modes: group-aware exclusion to avoid picking
        #   a group that overlaps with the already-resolved location.
        simple_exclusion = set()
        group_exclusion = set()
        if var_def.constraints and "must_differ_from" in var_def.constraints:
            ref = var_def.constraints["must_differ_from"]
            ref_vars = ref if isinstance(ref, list) else [ref]
            for ref_var in ref_vars:
                if ref_var in resolved:
                    simple_exclusion.add(resolved[ref_var])
                    group_exclusion |= self._get_location_exclusion_set(resolved[ref_var])

        if mode == LocationMode.OBJECT_LOCATION:
            candidates = [loc for loc in object_locations if loc not in simple_exclusion]
            if not candidates:
                raise ValueError(f"No object locations available after exclusion for {var_def.name}")
            return random.choice(candidates)

        elif mode == LocationMode.LOCATION_NAME:
            candidates = [loc for loc in location_names if loc not in group_exclusion]
            if not candidates:
                raise ValueError(f"No location names available after exclusion for {var_def.name}")
            return random.choice(candidates)

        else:  # LocationMode.ANY — 50/50 between OBJECT_LOCATION and LOCATION_NAME
            filtered_obj_locs = [loc for loc in object_locations if loc not in simple_exclusion]
            filtered_loc_names = [loc for loc in location_names if loc not in group_exclusion]

            if random.random() < 0.5 and filtered_obj_locs:
                return random.choice(filtered_obj_locs)
            elif filtered_loc_names:
                return random.choice(filtered_loc_names)
            elif filtered_obj_locs:
                return random.choice(filtered_obj_locs)
            else:
                raise ValueError(f"No locations available after exclusion for {var_def.name}")

    def _sort_by_dependency(self, variables: List[VariableDefinition]) -> List[VariableDefinition]:
        """Sort variables so dependencies come first."""
        # Build dependency graph
        deps: Dict[str, List[str]] = {}
        for v in variables:
            deps[v.name] = []
            if v.constraints:
                for key, value in v.constraints.items():
                    if isinstance(value, str) and value.startswith("$"):
                        deps[v.name].append(value)

        # Topological sort (simple implementation for small graphs)
        result: List[VariableDefinition] = []
        visited: set = set()
        var_map = {v.name: v for v in variables}

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for dep in deps.get(name, []):
                if dep in var_map:
                    visit(dep)
            result.append(var_map[name])

        for v in variables:
            visit(v.name)

        return result


def substitute_variables(template: str, resolved: Dict[str, str]) -> str:
    """Substitute all $VAR_NAME placeholders in a template string."""
    result = template
    for var_name in sorted(resolved, key=len, reverse=True):
        result = result.replace(var_name, resolved[var_name])
    return result


def expand_location(location_value: str, scene_config: SceneConfig) -> List[str]:
    """
    Expand a location value to its object locations.
    If location_value is a location name, return all object locations it maps to.
    Otherwise return the location as a single-item list.
    """
    if scene_config.location_names and location_value in scene_config.location_names:
        return scene_config.location_names[location_value]
    return [location_value]


def find_observe_positions_for_locations(
    locations: List[str],
    scene_config: SceneConfig
) -> List[str]:
    """
    Find observe positions that cover all given locations.
    Returns a list of observe position names that together cover all locations.
    """
    # Build a map of observe position -> set of locations it can observe
    observe_coverage: Dict[str, set] = {}
    for pos_name, pos_cfg in scene_config.positions.items():
        if pos_cfg.type == "OBSERVE" and pos_cfg.observable_locations:
            observe_coverage[pos_name] = set(pos_cfg.observable_locations)

    # Greedy set cover to find minimal set of observe positions
    remaining = set(locations)
    selected: List[str] = []

    while remaining:
        # Find the observe position that covers the most remaining locations
        best_pos = None
        best_coverage = 0
        for pos_name, coverage in observe_coverage.items():
            covered = len(coverage & remaining)
            if covered > best_coverage:
                best_coverage = covered
                best_pos = pos_name

        if best_pos is None or best_coverage == 0:
            # No observe position covers any remaining locations
            break

        selected.append(best_pos)
        remaining -= observe_coverage[best_pos]

    return selected


def find_pick_position(
    object_type: str,
    location: str,
    scene_config: SceneConfig
) -> Optional[str]:
    """Find a PICK position for the given object type at the given location."""
    for pos_name, pos_cfg in scene_config.positions.items():
        if (pos_cfg.type == "PICK" and
            pos_cfg.bound_type == object_type and
            pos_cfg.bound_location == location):
            return pos_name
    return None


def find_place_position(
    object_type: str,
    location: str,
    scene_config: SceneConfig
) -> Optional[str]:
    """Find a PLACE position for the given object type at the given location."""
    for pos_name, pos_cfg in scene_config.positions.items():
        if (pos_cfg.type == "PLACE" and
            pos_cfg.bound_type == object_type and
            pos_cfg.bound_location == location):
            return pos_name
    return None


def get_all_observe_positions(scene_config: SceneConfig) -> List[str]:
    """Get all OBSERVE position names from the scene config."""
    return [
        pos_name for pos_name, pos_cfg in scene_config.positions.items()
        if pos_cfg.type == "OBSERVE"
    ]


def is_location_group(location_value: str, scene_config: SceneConfig) -> bool:
    """Check if a location value is a group name (maps to multiple locations)."""
    return bool(
        scene_config.location_names
        and location_value in scene_config.location_names
    )


def get_sample_positions_for_locations(
    locations: List[str],
    scene_config: SceneConfig,
    limit: int = 6
) -> List[str]:
    """Get sample PICK position names (one per location) whose bound_location is in the given locations."""
    loc_set = set(locations)
    seen_locations: set = set()
    samples = []
    for pos_name, pos_cfg in scene_config.positions.items():
        if pos_cfg.type == "PICK" and pos_cfg.bound_location in loc_set and pos_cfg.bound_location not in seen_locations:
            seen_locations.add(pos_cfg.bound_location)
            samples.append(pos_name)
            if len(samples) >= limit:
                break
    return samples
