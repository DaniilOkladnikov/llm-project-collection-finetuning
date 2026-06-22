"""Inspect a generated dataset: print the entry with the longest output.

Usage
-----
Latest dataset in ``dataset_generation/datasets/``::

    python -m dataset_generation.explore

A specific file::

    python -m dataset_generation.explore datasets/dataset_20260607_102700.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

OUTPUT_DIR = Path(__file__).resolve().parent / "datasets"


def latest_dataset() -> Path:
    """Return the most recently written dataset file."""
    files = sorted(OUTPUT_DIR.glob("dataset_*.json"))
    if not files:
        raise FileNotFoundError(f"No datasets found in {OUTPUT_DIR}")
    return files[-1]


def explore_dataset(path: Optional[Path] = None) -> Dict:
    """Load a dataset and print the entry with the longest ``output``.

    Defaults to the most recently generated dataset. Returns that entry so
    callers can inspect it further.
    """
    if path is None:
        path = latest_dataset()
    with open(path, "r", encoding="utf-8") as f:
        dataset: List[Dict] = json.load(f)

    if not dataset:
        print(f"{path} is empty")
        return {}

    lengths = [len(e["output"]) for e in dataset]
    longest = max(dataset, key=lambda e: len(e["output"]))

    print(longest)
    print(f"dataset: {path}")
    print(f"entries: {len(dataset)}")
    print(f"output length  max: {max(lengths)}  "
          f"mean: {sum(lengths) / len(dataset):.1f}  min: {min(lengths)}")
    print(f"\nlongest output ({len(longest['output'])} chars):")
    print(f"  metadata: {json.dumps(longest['metadata'], ensure_ascii=False)}")
    print("-" * 60)
    print(longest["output"])
    print("-" * 60)
    return longest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", type=Path, default=None,
                    help="dataset JSON to inspect (default: latest in datasets/)")
    args = ap.parse_args()
    explore_dataset(args.path)


if __name__ == "__main__":
    main()
