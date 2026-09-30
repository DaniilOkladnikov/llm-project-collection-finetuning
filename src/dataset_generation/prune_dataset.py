"""Prune a generated dataset by dropping redundant input-output pairs.

Nothing inside a pair is ever edited -- whole pairs are kept or dropped. The
point is that the dataset is wildly uneven in how much each pair teaches:
19,879 of the 45,813 pairs in ``dataset_2026-09-26_15-33-31.json`` (43.4%)
carry only 12 distinct output *shapes* between them, and 40.3% of all pairs
have an output whose text appears verbatim 50 times or more. Training on all of
them re-pays a full ~1,800-token forward pass to re-learn a string the model
already emits perfectly (``REPORT.md``: loss 0.015 after one epoch).

Every behaviour must still be learned, bookkeeping included, so a single
uniform cap is wrong: "one output shape" means opposite things in different
families. ``tool_error`` is one byte-identical answer repeated 4,165 times --
400 examples teach it just as well. ``parse_objects`` is *also* one shape, but
its value differs per scene and deriving it from the position list is the skill
that fails in 76% of test runs; a shape-based quota collapses it to 9 pairs.
Hence four controls, keyed to where the learning actually lives:

``ABS_MECH``
    Output is a deterministic copy of something already in the input (e.g.
    ``position`` = the argument of the last ``move_robot_to``; verified across
    all 4,422 such pairs with zero exceptions). One fixed shape, nothing to
    generalise over. Absolute budget, spread round-robin across shapes.
``ABS_VALUE``
    Shape is near-constant but the value varies per scene and the value *is*
    the skill. Absolute budget, spread round-robin across distinct
    ``scene_id``, so the budget buys as many distinct worlds as it can.
``PER_SHAPE``
    Many fine-grained shapes; within-shape value variation is the
    generalisation signal. Keep ``K`` examples of each shape.
``PROTECT``
    Thin and failure-linked (``REPORT.md`` RC-3 / RC-4). Keep all -- 591 pairs.

On top of that, floors guarantee every ``(task_id, answer_label)`` keeps at
least ``FLOOR_LABEL`` pairs and every ``answer_macro`` at least
``FLOOR_MACRO``, so no behaviour can be starved by a budget edit.

Run with::

    python src/dataset_generation/prune_dataset.py [--in DATASET] [--K 2]

With no ``--in`` the newest ``dataset_*.json`` that is not itself a pruned
output wins. Writes ``<name>_pruned.json`` (same schema, original keys kept) and
``<name>_pruned_report.json`` (per-family counts + coverage, so a budget change
can be judged without launching a training run).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

_HERE = Path(__file__).resolve().parent
DATASET_DIRS = [_HERE, _HERE.parent / "finetuning" / "datasets"]

BLOCK_HEADERS = ("PROGRAM", "MEMORY", "RESOLUTION", "TOOL CALL", "TOOL RESULTS",
                 "ANSWER")

Pair = dict[str, Any]

# --- budgets -----------------------------------------------------------------
# Absolute keeps for families whose output is a deterministic copy of something
# in the input. The value is the total for the family; it is spread across the
# family's shapes, so e.g. bookkeeping's 7 shapes get ~100 each.
ABS_MECH = {
    "bookkeeping": 700,
    "tool_error": 400,
    "parseuser_program": 150,
    "trivial_res_call": 150,
    "prelude_program": 100,
    "prelude_getpos": 100,
}
# Absolute keeps for families whose shape is constant but whose value is the
# skill. Spread across distinct scenes rather than shapes.
ABS_VALUE = {
    "parse_objects": 500,
    "parse_locations": 500,
    "parse_obsmap": 400,
    "scans_merge": 900,
    "scans_edit": 250,
}
# Kept whole: too thin to cut, and both are sites of a ~100%-failure mode.
PROTECT = frozenset({"filter_eval_notempty", "parse_user_statechange"})

# K for every other family. 2 -> 4.85x fewer pairs, 3 -> 4.37x, 4 -> 4.02x.
PROFILES = {"target5x": 2, "conservative": 3, "gentle": 4}

FLOOR_LABEL = 3
FLOOR_MACRO = 20


# --- classification ----------------------------------------------------------

_QUOTED = re.compile(r'"[^"]*"')
_LIST = re.compile(r'\[[^\[\]]*\]')
_DICT = re.compile(r'\{[^{}]*\}')
_DIGITS = re.compile(r'\d+')
_LINENO = re.compile(r'^L\d+')
# A resolution line that says nothing beyond naming the program line it is for.
_TRIVIAL_RES = re.compile(r'^L\d+\s*(check gripper|check position|)\s*$')


def _abstract(line: str) -> str:
    """Strip scene-specific values so two pairs that make the same decision
    about different objects land on the same shape."""
    out = _QUOTED.sub('"S"', line)
    for _ in range(3):                      # nested dicts/lists, innermost first
        out = _DICT.sub("{D}", out)
        out = _LIST.sub("[L]", out)
    return _DIGITS.sub("#", out)


def _blocks(text: str) -> dict[str, list[str]]:
    """Split a rendered output into ``block name -> body lines``."""
    found: dict[str, list[str]] = defaultdict(list)
    for chunk in text.split("\n\n"):
        lines = chunk.split("\n")
        head = lines[0].strip()
        if head in BLOCK_HEADERS:
            found[head].extend(lines[1:])
    return found


def classify(output: str, metadata: dict[str, Any]) -> tuple[str, tuple]:
    """Return ``(family, shape)`` for one pair, from its output text alone.

    Order matters: the fixed-text families are matched by prefix first, because
    several of them would otherwise fall into the generic MEMORY / RESOLUTION
    cases below.
    """
    blocks = _blocks(output)
    task = metadata.get("task_id")
    mem_keys = tuple(line.split(" = ")[0] for line in blocks.get("MEMORY", []))
    calls = tuple(re.sub(r"\(.*", "", c).strip() for c in blocks.get("TOOL CALL", []))
    res = blocks.get("RESOLUTION", [])

    if metadata.get("error_injected"):
        return "tool_error", ()
    if output.startswith("PROGRAM\nL1 remember avaliable positions"):
        return "prelude_program", ()
    if output.startswith("RESOLUTION\nL1\n\nTOOL CALL\navaliable positions"):
        return "prelude_getpos", ()
    if output.startswith("PROGRAM\nL1 parse user"):
        return "parseuser_program", ()
    if output.startswith("RESOLUTION\nL2\n\nMEMORY\nobjects ="):
        return "parse_objects", ()
    if output.startswith("RESOLUTION\nL3\n\nMEMORY\nlocations ="):
        return "parse_locations", ()
    if output.startswith("RESOLUTION\nL4\n\nMEMORY\nobservation mapping ="):
        return "parse_obsmap", ()

    # parse user: turn 1 closes the prelude at L5, turns 2+ are a one-line
    # program at L1. A statechange ("you are holding X") writes gripper/held
    # here, which is RC-4's failure site, so it is split off.
    if (output.startswith("RESOLUTION\nL5\n\nMEMORY\ncursor = done")
            or output.startswith("RESOLUTION\nL1\n\nMEMORY\ncursor = done")):
        statechange = ("held" in mem_keys) or ("gripper" in mem_keys)
        family = "parse_user_statechange" if statechange else "parse_user"
        return family, (task, min(len(mem_keys), 5), "ANSWER" in blocks)

    if output.startswith("PROGRAM"):
        verbs = tuple(re.sub(r"^L\d+\s*", "", line).split()[0] if line.strip() else ""
                      for line in blocks.get("PROGRAM", []))
        return "task_program", (task, verbs)

    # MEMORY-only, or MEMORY plus the next call of an already-planned step.
    if mem_keys and not res and "PROGRAM" not in blocks and "ANSWER" not in blocks:
        if "explored observation positions" in mem_keys:
            return "scans_merge", ()        # locate_shapes -> scans, empties derived
        if "scans" in mem_keys:
            return "scans_edit", ()         # pick/place effect on scans
        return "bookkeeping", (mem_keys, calls)

    shape = tuple(_abstract(_LINENO.sub("Lk", line.strip()))[:70] for line in res)
    if "ANSWER" in blocks:
        return "answer", (task, metadata.get("answer_label"), shape)
    if any("where value is" in line for line in res):
        if any("where value is not empty" in line for line in res):
            return "filter_eval_notempty", (task, shape)
        return "filter_eval", (task, shape)
    if res and all(_TRIVIAL_RES.match(line.strip()) for line in res) and calls:
        return "trivial_res_call", (shape, calls)
    return "resolution", (task, shape, mem_keys, calls)


# --- sampling ----------------------------------------------------------------

def take_across(pairs: list[Pair], budget: int, key: Callable[[Pair], Any],
                rng: random.Random) -> list[Pair]:
    """Take ``budget`` pairs, round-robin across distinct ``key`` values.

    Rarest group first, one pass at a time, so a budget buys the widest spread
    it can instead of a random clump: at ``budget`` >= number of groups every
    group is represented before any group gets a second pair.
    """
    if budget >= len(pairs):
        return list(pairs)
    groups: dict[Any, list[Pair]] = defaultdict(list)
    for pair in pairs:
        groups[key(pair)].append(pair)
    for members in groups.values():
        rng.shuffle(members)
    order = sorted(groups.values(), key=len)
    taken: list[Pair] = []
    depth = 0
    while len(taken) < budget:
        progressed = False
        for members in order:
            if depth < len(members):
                taken.append(members[depth])
                progressed = True
                if len(taken) >= budget:
                    break
        if not progressed:                  # every group exhausted
            break
        depth += 1
    return taken


def prune(pairs: list[Pair], k: int, seed: int = 11) -> list[Pair]:
    """Apply the four controls, then top up to satisfy the coverage floors."""
    rng = random.Random(seed)
    by_family: dict[str, list[Pair]] = defaultdict(list)
    for pair in pairs:
        by_family[pair["family"]].append(pair)

    kept: list[Pair] = []
    for family, members in by_family.items():
        if family in PROTECT:
            kept.extend(members)
        elif family in ABS_MECH:
            kept.extend(take_across(members, ABS_MECH[family],
                                    lambda p: p["shape"], rng))
        elif family in ABS_VALUE:
            kept.extend(take_across(members, ABS_VALUE[family],
                                    lambda p: p["scene_id"], rng))
        else:
            shapes: dict[Any, list[Pair]] = defaultdict(list)
            for pair in members:
                shapes[pair["shape"]].append(pair)
            for group in shapes.values():
                rng.shuffle(group)
                kept.extend(group[:k])

    # Floors. A budget is a ceiling on redundancy, not a licence to drop a
    # behaviour entirely, so anything left under-represented is topped back up.
    kept_ids = {pair["key"] for pair in kept}
    floors: Iterable[tuple[Callable[[Pair], Any], int]] = (
        (lambda p: (p["task_id"], p["answer_label"]), FLOOR_LABEL),
        (lambda p: p["answer_macro"], FLOOR_MACRO),
    )
    for key, floor in floors:
        grouped: dict[Any, list[Pair]] = defaultdict(list)
        for pair in pairs:
            grouped[key(pair)].append(pair)
        for members in grouped.values():
            have = sum(1 for p in members if p["key"] in kept_ids)
            for pair in members:
                if have >= floor:
                    break
                if pair["key"] not in kept_ids:
                    kept_ids.add(pair["key"])
                    kept.append(pair)
                    have += 1
    return kept


# --- reporting ---------------------------------------------------------------

def _control_of(family: str) -> str:
    if family in PROTECT:
        return "PROTECT"
    if family in ABS_MECH:
        return "ABS_MECH"
    if family in ABS_VALUE:
        return "ABS_VALUE"
    return "PER_SHAPE"


COVERAGE_KEYS: list[tuple[str, Callable[[Pair], Any]]] = [
    ("output_shape", lambda p: (p["family"],) + p["shape"]),
    ("task_id", lambda p: p["task_id"]),
    ("task_answer_label", lambda p: (p["task_id"], p["answer_label"])),
    ("answer_macro", lambda p: p["answer_macro"]),
    ("scene_id", lambda p: p["scene_id"]),
    ("conversation_id", lambda p: p["conversation_id"]),
]


def build_report(pairs: list[Pair], kept: list[Pair], k: int, seed: int) -> dict:
    total_chars = sum(p["n_input"] for p in pairs)
    kept_chars = sum(p["n_input"] for p in kept)
    was = Counter(p["family"] for p in pairs)
    now = Counter(p["family"] for p in kept)

    families = {}
    for family, count in was.most_common():
        shapes = len({p["shape"] for p in pairs if p["family"] == family})
        families[family] = {
            "control": _control_of(family),
            "shapes": shapes,
            "was": count,
            "kept": now[family],
            "kept_pct": round(100 * now[family] / count, 1),
        }

    coverage = {}
    for name, key in COVERAGE_KEYS:
        before = {key(p) for p in pairs}
        after = {key(p) for p in kept}
        coverage[name] = {"distinct": len(before), "kept": len(after),
                          "missing": len(before - after)}

    return {
        "source_pairs": len(pairs),
        "kept_pairs": len(kept),
        "kept_pct": round(100 * len(kept) / len(pairs), 1),
        "pair_reduction": round(len(pairs) / len(kept), 2),
        "input_chars": total_chars,
        "kept_input_chars": kept_chars,
        "char_reduction": round(total_chars / kept_chars, 2),
        "k_per_shape": k,
        "seed": seed,
        "floors": {"task_answer_label": FLOOR_LABEL, "answer_macro": FLOOR_MACRO},
        "budgets": {"ABS_MECH": ABS_MECH, "ABS_VALUE": ABS_VALUE,
                    "PROTECT": sorted(PROTECT)},
        "families": families,
        "coverage": coverage,
    }


def print_report(report: dict) -> None:
    print(f"\n{'family':24} {'was':>7} {'kept':>7} {'%':>7} {'shapes':>7}  control")
    for family, row in report["families"].items():
        print(f"{family:24} {row['was']:7d} {row['kept']:7d} {row['kept_pct']:6.1f}% "
              f"{row['shapes']:7d}  {row['control']}")
    print(f"\n{'coverage':22} {'distinct':>9} {'kept':>7} {'missing':>8}")
    for name, row in report["coverage"].items():
        flag = "" if row["missing"] == 0 else "   <-- LOST"
        print(f"{name:22} {row['distinct']:9d} {row['kept']:7d} "
              f"{row['missing']:8d}{flag}")
    print(f"\npairs  {report['source_pairs']:,} -> {report['kept_pairs']:,} "
          f"({report['kept_pct']}%, {report['pair_reduction']}x fewer)")
    print(f"chars  {report['input_chars']:,} -> {report['kept_input_chars']:,} "
          f"({report['char_reduction']}x fewer)")


# --- driver ------------------------------------------------------------------

def newest_dataset() -> Path | None:
    """Newest ``dataset_*.json`` that is not itself a pruned output or a report."""
    found = []
    for directory in DATASET_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.glob("dataset*.json"):
            if path.stem.endswith("_report") or "_pruned" in path.stem:
                continue
            found.append(path)
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def load_pairs(path: Path) -> list[Pair]:
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    pairs: list[Pair] = []
    for key, record in raw.items():
        meta = record["metadata"]
        family, shape = classify(record["output"], meta)
        pairs.append({
            "key": key, "family": family, "shape": shape,
            "n_input": len(record["input"]),
            "task_id": meta.get("task_id"),
            "answer_label": meta.get("answer_label"),
            "answer_macro": meta.get("answer_macro"),
            "scene_id": meta.get("scene_id"),
            "conversation_id": meta.get("conversation_id"),
        })
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--in", dest="src", default=None,
                    help="dataset to prune (default: newest unpruned dataset_*.json)")
    ap.add_argument("--out", default=None, help="output path (default: <name>_pruned.json)")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="target5x",
                    help="preset K per output shape (default: target5x, K=2)")
    ap.add_argument("--K", type=int, default=None,
                    help="examples kept per output shape; overrides --profile")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    src = Path(args.src) if args.src else newest_dataset()
    if src is None or not src.is_file():
        sys.exit(f"no dataset found (looked in {', '.join(map(str, DATASET_DIRS))})")
    k = args.K if args.K is not None else PROFILES[args.profile]

    print(f"reading {src} ...")
    pairs = load_pairs(src)
    print(f"{len(pairs):,} pairs, {len({p['family'] for p in pairs})} families, "
          f"K={k}, seed={args.seed}")

    kept = prune(pairs, k, args.seed)
    report = build_report(pairs, kept, k, args.seed)
    print_report(report)

    lost = [name for name, row in report["coverage"].items()
            if row["missing"] and name not in ("scene_id", "conversation_id")]
    if lost:
        print(f"\n[warn] coverage lost for {', '.join(lost)} -- raise a budget or K")

    # Re-read the source and emit only the kept keys, so the pruned file carries
    # the pairs byte-for-byte and keeps its original ids (finetune.py sorts on
    # int(key), which is gap-safe, and the ids stay traceable to the full file).
    with src.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    kept_keys = {p["key"] for p in kept}
    pruned = {key: raw[key] for key in raw if key in kept_keys}

    out = Path(args.out) if args.out else src.with_name(f"{src.stem}_pruned.json")
    with out.open("w", encoding="utf-8") as fh:
        json.dump(pruned, fh, ensure_ascii=False, indent=1)
    report_path = out.with_name(f"{out.stem}_report.json")
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"\nwritten {out} ({out.stat().st_size / 1e6:.1f} MB)"
          f"\n        {report_path}")


if __name__ == "__main__":
    main()
