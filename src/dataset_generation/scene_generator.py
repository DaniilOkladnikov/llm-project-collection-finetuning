"""Random scene generator for the robot simulator.

Produces a scene dict in the same top-level config format used by the hand-made
scenes under ``scenes/`` (keys ``object_locations``, ``object_types``,
``positions``, ``robot_start``, ``objects``, ``location_names``). The result loads
directly through ``Simulation._cmd_load_scene``.

Two flavours are produced:
  * "mixed"    (90%) -- locations & types drawn across many drafts in scene_drafts.json
  * "original" (10%) -- a single draft from scene_drafts_original.json reproduced in full

Run as ``python scene_generator.py`` to print one random scene as JSON.
"""

from __future__ import annotations

import json
import os
import random
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))


# --- data loading -----------------------------------------------------------

def _load(name: str) -> Any:
    with open(os.path.join(_HERE, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _apply(pattern: str, obj_type: str, obj_loc: str) -> str:
    return pattern.format(obj_type=obj_type, obj_loc=obj_loc)


def _normalize_object_types(object_types: Any) -> Dict[str, List[str]]:
    """Map each type's canonical name to its choosable display names.

    Accepts both the current draft format -- ``{canonical: [synonym, ...]}`` --
    and the legacy list format ``[canonical, ...]`` (still used by
    scene_drafts_original.json). In every case the canonical name itself is the
    first choosable name, followed by any synonyms.
    """
    if isinstance(object_types, dict):
        return {c: [c] + list(syns) for c, syns in object_types.items()}
    return {c: [c] for c in object_types}


def _choose_type_name(names: List[str], rng: random.Random) -> str:
    """Pick one display name (canonical or a synonym) for a type."""
    return rng.choice(names)


def _pick_pattern_pools(
    patterns: Dict[str, List[str]], rng: random.Random
) -> Tuple[List[str], List[str]]:
    """Choose 1-3 pick patterns and (independently) 1-3 place patterns."""
    pick_pool = rng.sample(patterns["pick_patterns"], rng.randint(1, 3))
    place_pool = rng.sample(patterns["place_patterns"], rng.randint(1, 3))
    return pick_pool, place_pool


# --- position builders ------------------------------------------------------

def _pick_entry(obj_type: str, obj_loc: str) -> Dict[str, Any]:
    return {
        "type": "PICK",
        "bound_type": obj_type,
        "bound_location": obj_loc,
        "observable_locations": None,
    }


def _place_entry(obj_type: str, obj_loc: str) -> Dict[str, Any]:
    return {
        "type": "PLACE",
        "bound_type": obj_type,
        "bound_location": obj_loc,
        "observable_locations": None,
    }


def _observe_entry(locs: List[str]) -> Dict[str, Any]:
    return {
        "type": "OBSERVE",
        "bound_type": None,
        "bound_location": None,
        "observable_locations": list(locs),
    }


def _general_entry() -> Dict[str, Any]:
    return {
        "type": "GENERAL",
        "bound_type": None,
        "bound_location": None,
        "observable_locations": None,
    }


def _add_position(positions: Dict[str, Any], name: str, entry: Dict[str, Any]) -> None:
    # Pattern names embed both type and location, so collisions are not expected;
    # guard against an accidental duplicate that would silently drop a position.
    assert name not in positions, f"duplicate position name generated: {name!r}"
    positions[name] = entry


# --- observe set cover ------------------------------------------------------

def _min_observe_cover(
    chosen_locs: List[str],
    observe_groups: List[Tuple[str, List[str]]],
    rng: random.Random,
) -> List[Tuple[str, List[str]]]:
    """Smallest set of observe groups whose union covers every chosen location.

    Enumerates covers by increasing size over only the groups that intersect the
    chosen locations, collects all covers at the minimal size, and returns one at
    random. Each location belongs to a draft whose observe_dict partitions it, so a
    cover always exists.
    """
    target = set(chosen_locs)
    relevant = [
        (name, locs) for name, locs in observe_groups
        if target & set(locs)
    ]

    for size in range(1, len(relevant) + 1):
        covers = [
            combo for combo in combinations(relevant, size)
            if target <= set().union(*(set(locs) for _, locs in combo))
        ]
        if covers:
            return list(rng.choice(covers))

    # Unreachable given the data invariant, but fail loudly rather than silently.
    raise RuntimeError("no observe cover found for chosen locations")


# --- scene assembly ---------------------------------------------------------

def _assemble(
    object_locations: List[str],
    object_types: List[str],
    pick_positions: Dict[str, Any],
    place_positions: Dict[str, Any],
    observe_positions: Dict[str, Any],
    general_names: List[str],
    objects_by_type: Dict[str, int],
    location_names: Dict[str, List[str]],
) -> Dict[str, Any]:
    positions: Dict[str, Any] = {}
    positions.update(pick_positions)
    positions.update(place_positions)
    positions.update(observe_positions)
    for name in general_names:
        _add_position(positions, name, _general_entry())

    objects: Dict[str, Any] = {}
    next_id = 1
    for obj_type in object_types:
        for _ in range(objects_by_type.get(obj_type, 0)):
            objects[str(next_id)] = {
                "id": next_id,
                "type": obj_type,
                "location": "UNDEFINED",
            }
            next_id += 1

    return {
        "object_locations": list(object_locations),
        "object_types": list(object_types),
        "positions": positions,
        "robot_start": {"position": "home", "gripper_open": 1},
        "objects": objects,
        "location_names": location_names,
    }


def _ordered_generals(names: List[str]) -> List[str]:
    """`home` first, remaining unique names in insertion order."""
    ordered = ["home"]
    for name in names:
        if name not in ordered:
            ordered.append(name)
    return ordered


# --- original scenes --------------------------------------------------------

def _generate_original(
    originals: List[Dict[str, Any]],
    pools: Tuple[List[str], List[str]],
    rng: random.Random,
) -> Dict[str, Any]:
    pick_pool, place_pool = pools
    draft = rng.choice(originals)
    locs = list(draft["object_locations"])
    normalized = _normalize_object_types(draft["object_types"])
    types = [_choose_type_name(names, rng) for names in normalized.values()]

    pick_positions: Dict[str, Any] = {}
    place_positions: Dict[str, Any] = {}
    for obj_type in types:
        for loc in locs:
            _add_position(
                pick_positions, _apply(rng.choice(pick_pool), obj_type, loc),
                _pick_entry(obj_type, loc),
            )
            _add_position(
                place_positions, _apply(rng.choice(place_pool), obj_type, loc),
                _place_entry(obj_type, loc),
            )

    observe_positions: Dict[str, Any] = {}
    for name, obs_locs in draft["observe_dict"].items():
        _add_position(observe_positions, name, _observe_entry(obs_locs))

    general_names = _ordered_generals(list(draft.get("general_position_names", [])))

    # Every type sits at every location -> one object per location per type.
    objects_by_type = {obj_type: len(locs) for obj_type in types}

    return _assemble(
        object_locations=locs,
        object_types=types,
        pick_positions=pick_positions,
        place_positions=place_positions,
        observe_positions=observe_positions,
        general_names=general_names,
        objects_by_type=objects_by_type,
        location_names=dict(draft["location_names"]),
    )


# --- mixed scenes -----------------------------------------------------------

def _empty_intersection_quad(group_locs: List[frozenset]) -> bool:
    """True if some 4 of the given fully-covered groups share no common location.

    "4 location names with empty intersection" means four named groups whose
    common intersection is empty -- no single location belongs to all four.
    """
    for combo in combinations(group_locs, 4):
        if not frozenset.intersection(*combo):
            return True
    return False


def _choose_locations(
    all_groups: List[Tuple[str, frozenset, int]],
    rng: random.Random,
) -> List[str]:
    """Pick 4-20 locations such that 4 named groups with empty common
    intersection are fully covered."""
    while True:
        groups = list(all_groups)
        rng.shuffle(groups)

        chosen: set = set()
        covered: List[frozenset] = []
        for _name, locs, _idx in groups:
            if len(chosen | locs) > 20:
                continue
            chosen |= locs
            if locs not in covered:
                covered.append(locs)
            if (len(covered) >= 4 and 4 <= len(chosen) <= 20
                    and _empty_intersection_quad(covered)):
                break

        if (len(covered) < 4 or not (4 <= len(chosen) <= 20)
                or not _empty_intersection_quad(covered)):
            continue  # retry with a fresh shuffle

        # Grow to a random target size in [len(chosen), 20] with extra individual
        # locations, so scenes vary in size rather than always hitting the cap.
        target = rng.randint(len(chosen), 20)
        pool = [loc for _n, locs, _i in all_groups for loc in locs if loc not in chosen]
        rng.shuffle(pool)
        for loc in pool:
            if len(chosen) >= target:
                break
            chosen.add(loc)

        return list(chosen)


def _generate_mixed(
    drafts: List[Dict[str, Any]],
    pools: Tuple[List[str], List[str]],
    rng: random.Random,
) -> Dict[str, Any]:
    pick_pool, place_pool = pools

    loc_to_draft: Dict[str, int] = {}
    all_groups: List[Tuple[str, frozenset, int]] = []
    all_observe: List[Tuple[str, List[str]]] = []
    all_types: List[str] = []
    type_names: Dict[str, List[str]] = {}
    for idx, draft in enumerate(drafts):
        for loc in draft["object_locations"]:
            loc_to_draft[loc] = idx
        for name, locs in draft.get("location_names", {}).items():
            all_groups.append((name, frozenset(locs), idx))
        for name, locs in draft.get("observe_dict", {}).items():
            all_observe.append((name, list(locs)))
        for canonical, names in _normalize_object_types(draft["object_types"]).items():
            if canonical not in type_names:
                all_types.append(canonical)
                type_names[canonical] = list(names)
            else:
                for name in names:  # merge synonyms seen in other drafts
                    if name not in type_names[canonical]:
                        type_names[canonical].append(name)

    # A location is only usable if some observe group can see it (picking requires
    # a prior observe). Drop location_names groups that reference any location no
    # observe group covers -- these are draft typos (e.g. "binB_002").
    observable_universe = {loc for _n, locs in all_observe for loc in locs}
    all_groups = [
        (name, locs, idx) for name, locs, idx in all_groups
        if locs <= observable_universe
    ]

    # Step 1: locations.
    chosen_locs = _choose_locations(all_groups, rng)

    # Step 2: 4-10 object types, each rendered as its canonical name or a synonym.
    n_types = rng.randint(4, min(10, len(all_types)))
    types = [
        _choose_type_name(type_names[canonical], rng)
        for canonical in rng.sample(all_types, n_types)
    ]

    # Step 3: which (type, loc) pairs get pick+place positions.
    pairs: set = set()
    t4 = rng.sample(types, 4)
    l4 = rng.sample(chosen_locs, 4)
    for t in t4:
        for l in l4:
            pairs.add((t, l))
    for t in types:
        for l in chosen_locs:
            if (t, l) not in pairs and rng.random() < 0.5:
                pairs.add((t, l))

    # Repair: every type and every location must appear at least once.
    types_with = {t for t, _ in pairs}
    locs_with = {l for _, l in pairs}
    for t in types:
        if t not in types_with:
            pairs.add((t, rng.choice(chosen_locs)))
    for l in chosen_locs:
        if l not in locs_with:
            pairs.add((rng.choice(types), l))

    pick_positions: Dict[str, Any] = {}
    place_positions: Dict[str, Any] = {}
    objects_by_type: Dict[str, int] = {t: 0 for t in types}
    for obj_type, loc in pairs:
        _add_position(
            pick_positions, _apply(rng.choice(pick_pool), obj_type, loc),
            _pick_entry(obj_type, loc),
        )
        _add_position(
            place_positions, _apply(rng.choice(place_pool), obj_type, loc),
            _place_entry(obj_type, loc),
        )
        objects_by_type[obj_type] += 1

    # Step 5: observe positions (smallest cover, trimmed to scene) + location_names.
    chosen_set = set(chosen_locs)
    cover = _min_observe_cover(chosen_locs, all_observe, rng)
    observe_positions: Dict[str, Any] = {}
    for name, obs_locs in cover:
        trimmed = [loc for loc in obs_locs if loc in chosen_set]
        _add_position(observe_positions, name, _observe_entry(trimmed))

    location_names = _covered_location_names(drafts, chosen_set)

    # Step 6: general positions.
    contributing = {loc_to_draft[loc] for loc in chosen_locs}
    general_candidates: List[str] = []
    for idx in contributing:
        for name in drafts[idx].get("general_position_names", []):
            if name == "home":
                continue
            if rng.random() < 0.5:
                general_candidates.append(name)
    general_names = _ordered_generals(general_candidates)

    # Step 8: config reflects exactly what is used (every chosen loc/type has a pair).
    used_types = [t for t in types if objects_by_type[t] > 0]
    used_locs = [l for l in chosen_locs if l in {loc for _, loc in pairs}]

    return _assemble(
        object_locations=used_locs,
        object_types=used_types,
        pick_positions=pick_positions,
        place_positions=place_positions,
        observe_positions=observe_positions,
        general_names=general_names,
        objects_by_type=objects_by_type,
        location_names=location_names,
    )


def _covered_location_names(
    drafts: List[Dict[str, Any]], chosen_set: set
) -> Dict[str, List[str]]:
    """All location_names groups (any draft) fully contained in chosen_set,
    preserving each group's original location ordering."""
    result: Dict[str, List[str]] = {}
    for draft in drafts:
        for name, locs in draft.get("location_names", {}).items():
            if set(locs) <= chosen_set and name not in result:
                result[name] = list(locs)
    return result


# --- public entry -----------------------------------------------------------

def generate_scene(rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """Return a random scene dict loadable by the simulator."""
    rng = rng or random.Random()

    patterns = _load("patterns.json")
    drafts = _load("scene_drafts.json")
    originals = _load("scene_drafts_original.json")

    pools = _pick_pattern_pools(patterns, rng)

    if rng.random() < 0.90:
        return _generate_mixed(drafts, pools, rng)
    return _generate_original(originals, pools, rng)


if __name__ == "__main__":
    print(json.dumps(generate_scene()["object_types"], indent=2))
