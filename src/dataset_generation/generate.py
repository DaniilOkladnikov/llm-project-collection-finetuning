"""Driver: run every task across every scene N times and save the dataset.

Each LLM invocation becomes one ``{input, output, metadata}`` entry (full
fidelity, including CHECK passes). Output is written to
``dataset_generation/datasets/dataset_<YYYYMMDD_HHMMSS>.json``.

Examples
--------
Full cross-product (all tasks x all scenes x 3)::

    python -m dataset_generation.generate

Smoke run on two scenes, capped::

    python -m dataset_generation.generate --scenes scene_box_11_cube,scene_binA_001_gear --cap 200
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tool_simulation_server import config as sim_config

from .resolve import IncompatibleScenario
from .runner import run_scenario
from .tasks import TASKS

OUTPUT_DIR = Path(__file__).resolve().parent / "datasets"
# repo root: .../llm-project-collection/finetuning/src/dataset_generation/generate.py
_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_scenes_dir() -> Path:
    """Find the scenes directory, tolerating the installed package's stale path."""
    candidates = [
        Path(sim_config.SCENES_DIR),
        _REPO_ROOT / "tool-simulation-server" / "scenes",
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.json")):
            return c
    raise FileNotFoundError(
        f"No scenes directory found. Tried: {[str(c) for c in candidates]}")


def _seed(task_id: str, scene: str, i: int) -> int:
    return hash((task_id, scene, i)) % (2 ** 31)


def generate(
    scenes: Optional[List[str]] = None,
    task_ids: Optional[List[str]] = None,
    per: int = 3,
    cap: Optional[int] = None,
    out: Optional[Path] = None,
) -> Path:
    scene_dir = resolve_scenes_dir()
    scene_paths = sorted(scene_dir.glob("*.json"))
    if scenes:
        wanted = set(scenes)
        scene_paths = [p for p in scene_paths if p.stem in wanted]

    tasks = TASKS
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in TASKS if t.id in wanted]

    print(f"{len(tasks)} tasks x {len(scene_paths)} scenes x {per} = "
          f"{len(tasks) * len(scene_paths) * per} scenarios")

    dataset: List[Dict] = []
    generated = skipped = failed = scenarios = 0
    by_task: Counter = Counter()

    stop = False
    for scene_path in scene_paths:
        if stop:
            break
        for task in tasks:
            for i in range(per):
                if cap is not None and len(dataset) >= cap:
                    stop = True
                    break
                scenarios += 1
                seed = _seed(task.id, scene_path.stem, i)
                try:
                    entries = run_scenario(task, scene_path, seed)
                except IncompatibleScenario:
                    skipped += 1
                    continue
                except Exception as e:  # pragma: no cover - defensive
                    failed += 1
                    print(f"  FAIL {task.id} @ {scene_path.stem} seed={seed}: "
                          f"{type(e).__name__}: {e}")
                    continue
                for entry in entries:
                    dataset.append({
                        "input": entry.input,
                        "output": entry.output,
                        "metadata": entry.metadata,
                    })
                generated += 1
                by_task[task.id] += 1
            if stop:
                break

    print(f"\nscenarios attempted: {scenarios}")
    print(f"  generated: {generated}   skipped (incompatible): {skipped}   failed: {failed}")
    print(f"  dataset entries (invocations): {len(dataset)}")

    if out is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / f"dataset_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"saved {len(dataset)} entries to {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenes", help="comma-separated scene stems (default: all)")
    ap.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ap.add_argument("--per", type=int, default=3,
                    help="scenarios per (task, scene) (default: 3)")
    ap.add_argument("--cap", type=int, default=None,
                    help="stop after this many dataset entries (smoke runs)")
    ap.add_argument("--out", type=Path, default=None, help="explicit output path")
    args = ap.parse_args()

    generate(
        scenes=args.scenes.split(",") if args.scenes else None,
        task_ids=args.tasks.split(",") if args.tasks else None,
        per=args.per,
        cap=args.cap,
        out=args.out,
    )


if __name__ == "__main__":
    main()
