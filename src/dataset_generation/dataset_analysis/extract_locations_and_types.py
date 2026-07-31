"""Extract grouped locations and unique object types from scene_drafts.json.

Locations are grouped one-scene-per-group: each scene's ``object_locations``
list becomes one group, keyed by a human-meaningful name (see GROUP_NAMES,
curated per scene in file order). Output is a JSON object of the form
``{"group name": ["location1", "location2", ...], ...}``.

Object types come from each scene's ``object_types`` dict: every canonical
key AND every synonym in its value list counts as a distinct object type
(e.g. ``"washer": ["spacer", "shim_ring"]`` yields three object types:
``washer``, ``spacer``, ``shim_ring``). Output is a sorted list of unique
strings.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT_PATH = HERE / "scene_drafts.json"
LOCATIONS_PATH = HERE / "locations_grouped.json"
OBJECT_TYPES_PATH = HERE / "object_types.json"

# One name per scene, in the order scenes appear in scene_drafts.json.
# Names are curated from each scene's locations/context. If the file gains
# more scenes than there are names here, extras fall back to "scene_<n>".
GROUP_NAMES = [
    "quadrant_tables",                     # table_Q1..Q4
    "assembly_workbenches",                # workbench_A1/A2 + small parts drawer
    "color_sorting_bins",                  # red/blue bins + waste chute
    "feed_tray_slots",                     # infeed/outfeed tray slots
    "conveyor_inspection_stations",        # conveyor pick/drop + inspection pad
    "rack_and_cart_positions",             # rack top/middle/bottom + cart front/back
    "three_by_four_slot_grid",             # slot1_1..slot3_4
    "warehouse_aisle_bins",                # binA/binB/binC openings
    "chessboard_back_rank",                # chess_a1..h1 + captured pieces
    "recycling_containers_and_quadrants",  # metal/debris/electronic + clearing quadrants
    "processing_stations",                 # station_alpha/beta/gamma + buffer zone
    "eighteen_parcel_zones",               # zone_001..zone_018
    "cylinder_storage_bays",               # bay_A/B/C + overflow rack
    "coordinate_pose_grid",                # pos.y0.x0..pos.y2.x3
    "egg_nests",                           # nest_1..nest_5
    "chip_sorting_slots",                  # primary/secondary/tertiary + reject tray
    "four_by_five_well_plate",             # cell_R1C1..cell_R4C5
    "coat_room_hooks",                     # hook_1..hook_6 + bin floor
    "foundry_stations",                    # furnace/ingot queue/cooling/finished stack
    "inspection_lanes",                    # lane_1..lane_3 sections + reject/pass bins
    "bead_dispensers",                     # dispenser_A..D
    "pharmacy_drawers",                    # drawer_1..drawer_10 + countertop
    "grain_silos",                         # silo_1..silo_3
    "painting_station",                    # palette wells + canvas zones + water/rag
    "coin_sorter_bins",                    # input chute + coin bins + reject slot
    "warehouse_shelf_slots",               # shelf_L1..L3 slots + packing/shipping
    "kitchen_stove_stations",              # pots + burners + prep board + sink
    "tire_shop_bays",                      # tire bays + racks + balancer + disposal
    "apple_orchard_trees",                 # tree_1..tree_15 + collection/sorting
]


def main() -> None:
    with INPUT_PATH.open(encoding="utf-8") as f:
        scenes = json.load(f)

    grouped_locations: dict[str, list[str]] = {}
    object_types: set[str] = set()

    for i, scene in enumerate(scenes):
        name = GROUP_NAMES[i] if i < len(GROUP_NAMES) else f"scene_{i + 1}"
        # Guard against accidental duplicate names collapsing groups.
        if name in grouped_locations:
            name = f"{name}_{i + 1}"
        grouped_locations[name] = scene.get("object_locations", [])

        for canonical, synonyms in scene.get("object_types", {}).items():
            object_types.add(canonical)
            object_types.update(synonyms)

    sorted_object_types = sorted(object_types)

    with LOCATIONS_PATH.open("w", encoding="utf-8") as f:
        json.dump(grouped_locations, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with OBJECT_TYPES_PATH.open("w", encoding="utf-8") as f:
        json.dump(sorted_object_types, f, indent=2, ensure_ascii=False)
        f.write("\n")

    total_locations = sum(len(v) for v in grouped_locations.values())
    print(f"Scenes processed:     {len(scenes)}")
    print(f"Location groups:      {len(grouped_locations)} "
          f"({total_locations} locations) -> {LOCATIONS_PATH.name}")
    print(f"Unique object types:  {len(sorted_object_types)} -> {OBJECT_TYPES_PATH.name}")


if __name__ == "__main__":
    main()
