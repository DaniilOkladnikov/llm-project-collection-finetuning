"""Reverse-engineer the scenes embedded in a generated finetuning dataset.

Every conversation in the dataset shows its scene to the model through a single
channel -- the ``avaliable positions`` tool result, a flat list of position
names (see ``scene_model.py``). The object-instance list, occupancy and location
groupings are never shown to the model, so that position list *is* the scene.

Each name in the list is exactly one of four things:

  * a PICK position    -- a ``pick_patterns`` template filled with (type, loc)
  * a PLACE position   -- a ``place_patterns`` template filled with (type, loc)
  * an OBSERVE position -- a key of some draft's ``observe_dict``
  * a GENERAL position  -- a name in some draft's ``general_position_names``

This script walks a dataset, pulls out every distinct position list, and parses
each one back into the four things a scene is built from -- objects (types),
locations, observe positions and general positions -- using patterns.json and
the scene drafts as the vocabulary. The result is written to a JSON file.

The pick/place templates and the draft vocabulary are the same ones
``scene_generator.py`` uses to *build* scenes; this is the inverse.

Run:  python scene_extractor.py [--dataset PATH ...] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DATASET = os.path.normpath(
    os.path.join(_HERE, "..", "finetuning", "datasets", "dataset.json")
)
_DEFAULT_OUT = os.path.join(_HERE, "extracted_scenes.json")
_DEFAULT_OBSERVE_OUT = os.path.join(_HERE, "extracted_observe_positions.json")
_DRAFT_FILES = ["scene_drafts.json", "scene_drafts_original.json"]


# --- data loading -----------------------------------------------------------

def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalize_object_types(object_types: Any) -> Dict[str, List[str]]:
    """Every choosable display name for each type (canonical + synonyms).

    Mirrors ``scene_generator._normalize_object_types`` so the names we look for
    are exactly the names the generator could have emitted -- it accepts both the
    dict draft format and the legacy list format of the original drafts.
    """
    if isinstance(object_types, dict):
        return {c: [c] + list(syns) for c, syns in object_types.items()}
    return {c: [c] for c in object_types}


# --- vocabulary from the drafts ---------------------------------------------

class Vocabulary:
    """The universe of names a scene can be assembled from, drawn from every
    draft. Locations and type display names feed the pick/place regexes; observe
    keys and general names are matched directly."""

    def __init__(self, draft_files: List[str]) -> None:
        self.locations: set = set()
        self.type_names: set = set()
        self.observe: Dict[str, List[str]] = {}   # name -> ordered locations
        self.general: set = set()

        for path in draft_files:
            if not os.path.exists(path):
                continue
            for draft in _load(path):
                self.locations.update(draft.get("object_locations", []))
                for names in _normalize_object_types(draft.get("object_types", {})).values():
                    self.type_names.update(names)
                for name, locs in draft.get("observe_dict", {}).items():
                    # Same key in two drafts -> keep every location it can see.
                    seen = self.observe.setdefault(name, [])
                    for loc in locs:
                        if loc not in seen:
                            seen.append(loc)
                self.general.update(draft.get("general_position_names", []))


# --- pattern reversal -------------------------------------------------------

def _alternation(items: set) -> str:
    """Regex alternation of the items, longest first so that greedy matching
    prefers the longest valid token (matters for delimiter-less templates)."""
    return "|".join(re.escape(x) for x in sorted(items, key=lambda s: (-len(s), s)))


def _compile_patterns(templates: List[str], type_alt: str, loc_alt: str) -> List[re.Pattern]:
    """Turn each ``{obj_type}``/``{obj_loc}`` template into an anchored regex
    whose two capture groups are constrained to the known type/location tokens."""
    compiled: List[re.Pattern] = []
    for tmpl in templates:
        parts = re.split(r"(\{obj_type\}|\{obj_loc\})", tmpl)
        rx = ["^"]
        for part in parts:
            if part == "{obj_type}":
                rx.append("(?P<obj_type>" + type_alt + ")")
            elif part == "{obj_loc}":
                rx.append("(?P<obj_loc>" + loc_alt + ")")
            elif part:
                rx.append(re.escape(part))
        rx.append("$")
        compiled.append(re.compile("".join(rx)))
    return compiled


class SceneParser:
    """Classifies a single position name and rebuilds a scene from a name list."""

    def __init__(self, patterns: Dict[str, List[str]], vocab: Vocabulary) -> None:
        self.vocab = vocab
        type_alt = _alternation(vocab.type_names)
        loc_alt = _alternation(vocab.locations)
        self.pick_rx = _compile_patterns(patterns["pick_patterns"], type_alt, loc_alt)
        self.place_rx = _compile_patterns(patterns["place_patterns"], type_alt, loc_alt)

    def classify(self, name: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Return ``(role, type, loc)``; type/loc are None for OBSERVE/GENERAL."""
        if name in self.vocab.observe:
            return ("OBSERVE", None, None)
        if name in self.vocab.general:
            return ("GENERAL", None, None)
        for rx in self.pick_rx:
            m = rx.match(name)
            if m:
                return ("PICK", m.group("obj_type"), m.group("obj_loc"))
        for rx in self.place_rx:
            m = rx.match(name)
            if m:
                return ("PLACE", m.group("obj_type"), m.group("obj_loc"))
        return ("UNKNOWN", None, None)

    def reconstruct(self, names: List[str]) -> Dict[str, Any]:
        objects: List[str] = []
        used_locs: List[str] = []
        observe_names: List[str] = []
        general_names: List[str] = []
        unknown: List[str] = []
        obj_seen, loc_seen = set(), set()

        for name in names:
            role, obj_type, loc = self.classify(name)
            if role in ("PICK", "PLACE"):
                if obj_type not in obj_seen:
                    obj_seen.add(obj_type)
                    objects.append(obj_type)
                if loc not in loc_seen:
                    loc_seen.add(loc)
                    used_locs.append(loc)
            elif role == "OBSERVE":
                observe_names.append(name)
            elif role == "GENERAL":
                general_names.append(name)
            else:
                unknown.append(name)

        used = set(used_locs)
        # Observe poses see only the scene's own locations (the generator trims
        # each pose to the chosen locations); rebuild that trimmed view.
        observe_positions: Dict[str, List[str]] = {}
        canonical: List[str] = []
        can_seen: set = set()
        for name in observe_names:
            locs = [loc for loc in self.vocab.observe.get(name, []) if loc in used]
            observe_positions[name] = locs
            for loc in locs:
                if loc not in can_seen:
                    can_seen.add(loc)
                    canonical.append(loc)
        # Canonical location order = first appearance across observe poses, then
        # any pick/place-only locations (mirrors SceneModel.canonical_order).
        for loc in used_locs:
            if loc not in can_seen:
                can_seen.add(loc)
                canonical.append(loc)

        scene: Dict[str, Any] = {
            "objects": objects,
            "locations": canonical,
            "observe_positions": observe_positions,
            "general_positions": general_names,
        }
        if unknown:
            scene["unknown_positions"] = unknown
        return scene


# --- pulling position lists out of the dataset ------------------------------

_BLOCK_RE = re.compile(r"avaliable positions = \{")
_DECODER = json.JSONDecoder()


def _iter_position_lists(text: str) -> Iterator[List[str]]:
    """Yield every ``avaliable positions`` content list found in a message.

    The MEMORY block is Python-ish (``{status: "OK", content: [...]}``) and not
    valid JSON, but the content array itself is a proper JSON array of strings --
    element strings may contain ``[``/``]`` -- so decode it with ``raw_decode``
    from the opening bracket rather than trying to balance brackets by hand.
    """
    for block in _BLOCK_RE.finditer(text):
        head = text.find("content:", block.end())
        if head == -1:
            continue
        start = text.find("[", head)
        if start == -1:
            continue
        try:
            arr, _ = _DECODER.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
            yield arr


def _iter_examples(data: Any) -> Iterator[Dict[str, Any]]:
    """Datasets are stored either as an id->example dict or a list of examples."""
    items = data.values() if isinstance(data, dict) else data
    for ex in items:
        if isinstance(ex, dict):
            yield ex


def collect_scenes(dataset_paths: List[str]) -> Dict[Tuple[str, ...], Dict[str, Any]]:
    """Distinct scenes keyed by the sorted tuple of their position names."""
    scenes: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for path in dataset_paths:
        for ex in _iter_examples(_load(path)):
            conv_id = ex.get("metadata", {}).get("conversation_id")
            for names in _iter_position_lists(ex.get("input", "")):
                key = tuple(sorted(names))
                slot = scenes.setdefault(key, {"names": list(names), "convs": set()})
                if conv_id is not None:
                    slot["convs"].add(conv_id)
    return scenes


# --- public entry -----------------------------------------------------------

def extract(dataset_paths: List[str], parser: SceneParser) -> List[Dict[str, Any]]:
    scenes = collect_scenes(dataset_paths)
    ordered = sorted(
        scenes.values(),
        key=lambda s: (min(s["convs"]) if s["convs"] else 1 << 30),
    )
    out: List[Dict[str, Any]] = []
    for i, slot in enumerate(ordered):
        rec = parser.reconstruct(slot["names"])
        out.append({
            "scene_id": i,
            "objects": rec["objects"],
            "locations": rec["locations"],
            "observe_positions": rec["observe_positions"],
            "general_positions": rec["general_positions"],
            **({"unknown_positions": rec["unknown_positions"]}
               if "unknown_positions" in rec else {}),
            "num_positions": len(slot["names"]),
            "num_source_conversations": len(slot["convs"]),
            "source_conversation_ids": sorted(slot["convs"]),
        })
    return out


def count_unique(scenes: List[Dict[str, Any]]) -> Dict[str, int]:
    """Distinct objects, locations and observe positions across all scenes
    (scenes are already deduplicated, so their count is the unique-scene count)."""
    objects: set = set()
    locations: set = set()
    observe: set = set()
    for scene in scenes:
        objects.update(scene["objects"])
        locations.update(scene["locations"])
        observe.update(scene["observe_positions"])
    return {
        "scenes": len(scenes),
        "objects": len(objects),
        "locations": len(locations),
        "observe_positions": len(observe),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", nargs="+", default=[_DEFAULT_DATASET],
                    help="dataset JSON file(s) to scan (default: %(default)s)")
    ap.add_argument("--out", default=_DEFAULT_OUT,
                    help="where to write the extracted scenes (default: %(default)s)")
    ap.add_argument("--observe-out", default=_DEFAULT_OBSERVE_OUT,
                    help="where to write just the per-scene observe_positions "
                         "dicts (default: %(default)s)")
    ap.add_argument("--patterns", default=os.path.join(_HERE, "patterns.json"),
                    help="pick/place pattern templates")
    ap.add_argument("--drafts", nargs="+",
                    default=[os.path.join(_HERE, f) for f in _DRAFT_FILES],
                    help="scene draft file(s) supplying the name vocabulary")
    args = ap.parse_args()

    vocab = Vocabulary(args.drafts)
    parser = SceneParser(_load(args.patterns), vocab)
    scenes = extract(args.dataset, parser)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(scenes, fh, indent=2)

    # A companion file holding only the observe_positions dicts, one per scene
    # (list index == scene_id).
    observe_dicts = [s["observe_positions"] for s in scenes]
    with open(args.observe_out, "w", encoding="utf-8") as fh:
        json.dump(observe_dicts, fh, indent=2)

    n_unknown = sum(1 for s in scenes if s.get("unknown_positions"))
    total_convs = sum(s["num_source_conversations"] for s in scenes)
    counts = count_unique(scenes)
    print(f"scanned    : {', '.join(args.dataset)}")
    print(f"written to : {os.path.abspath(args.out)}")
    print(f"observe to : {os.path.abspath(args.observe_out)}")
    print(f"conversations      : {total_convs}")
    print("unique in dataset ---------------")
    print(f"  scenes           : {counts['scenes']}")
    print(f"  objects          : {counts['objects']}")
    print(f"  locations        : {counts['locations']}")
    print(f"  observe positions: {counts['observe_positions']}")
    if n_unknown:
        print(f"WARNING     : {n_unknown} scene(s) contain positions that could "
              f"not be reverse-engineered (see 'unknown_positions')")


if __name__ == "__main__":
    main()
