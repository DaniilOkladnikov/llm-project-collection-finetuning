"""Delete Llama-3.2-3B GGUFs that have no test_rand counterpart.

The 3.2-3B sweep produced one GGUF per hyperparameter combination, but only a
handful of those combinations were re-run against the randomized test split.
A run is worth keeping only if that second run exists, so the keep set is:

    Llama-3.2-3B_<cfg>_test_rand_q8_0.gguf   (the test_rand run itself)
    Llama-3.2-3B_<cfg>_q8_0.gguf             (its plain twin)

Everything else matching Llama-3.2-3B goes. Other families (3.1-8B, 3.2-1B) are
never touched, and DSL adapters are excluded by default -- they are current work
with no test_rand runs yet, so the pairing rule would otherwise wipe them.

Deletes on invocation. Use --dry-run to see the list without removing anything.

Usage:
    python prune_gguf.py [--dry-run] [--include-dsl] [--gguf-dir PATH]
"""

import argparse
import sys
from pathlib import Path

GGUF_DIR = Path("D:/MyLLMs/gguf")

MODEL_FAMILY = "3.2-3B"
PAIR_MARKER = "test_rand"
QUANT_SUFFIX = "_q8_0.gguf"
DSL_MARKER = "DSL"


def counterpart_name(name: str) -> str:
    """Name of the test_rand twin for a plain GGUF.

    The marker sits between the config and the quant suffix, so
    '..._ep1_q8_0.gguf' pairs with '..._ep1_test_rand_q8_0.gguf'.
    """
    return name.replace(QUANT_SUFFIX, f"_{PAIR_MARKER}{QUANT_SUFFIX}")


def select_for_deletion(gguf_dir: Path, include_dsl: bool) -> tuple[list[Path], list[Path]]:
    """Return (to_delete, to_keep) for the target family only."""
    family = [
        p for p in sorted(gguf_dir.iterdir())
        if p.suffix == ".gguf" and MODEL_FAMILY in p.name
    ]

    have_counterpart = {p.name for p in family if PAIR_MARKER in p.name}

    to_delete, to_keep = [], []
    for path in family:
        if PAIR_MARKER in path.name:
            to_keep.append(path)                      # the counterpart itself
        elif counterpart_name(path.name) in have_counterpart:
            to_keep.append(path)                      # paired plain run
        elif DSL_MARKER in path.name and not include_dsl:
            to_keep.append(path)                      # excluded by default
        else:
            to_delete.append(path)

    return to_delete, to_keep


def format_gb(paths: list[Path]) -> str:
    return f"{sum(p.stat().st_size for p in paths) / 1e9:.1f} GB"


def main():
    parser = argparse.ArgumentParser(
        description=f"Delete {MODEL_FAMILY} GGUFs lacking a {PAIR_MARKER} counterpart",
    )
    parser.add_argument(
        "--gguf-dir", type=Path, default=GGUF_DIR,
        help="Directory containing the GGUF files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List what would be deleted, then exit without deleting",
    )
    parser.add_argument(
        "--include-dsl", action="store_true",
        help=f"Also delete unpaired {DSL_MARKER} runs (kept by default)",
    )
    args = parser.parse_args()

    if not args.gguf_dir.is_dir():
        print(f"Not a directory: {args.gguf_dir}")
        sys.exit(1)

    to_delete, to_keep = select_for_deletion(args.gguf_dir, args.include_dsl)

    print(f"{args.gguf_dir}  --  {MODEL_FAMILY} family\n")
    print(f"Keeping {len(to_keep)} ({format_gb(to_keep)}):")
    for path in to_keep:
        print(f"  {path.name}")

    if not to_delete:
        print("\nNothing to delete.")
        return

    print(f"\nDeleting {len(to_delete)} ({format_gb(to_delete)}):")
    for path in to_delete:
        print(f"  {path.name}")

    if args.dry_run:
        print("\nDry run -- nothing deleted.")
        return

    print()
    freed, failed = 0, 0
    for path in to_delete:
        size = path.stat().st_size
        try:
            path.unlink()
        except OSError as e:
            print(f"  FAILED {path.name}: {e}")
            failed += 1
            continue
        freed += size

    print(f"\nDeleted {len(to_delete) - failed} files, freed {freed / 1e9:.1f} GB"
          + (f", {failed} failed" if failed else ""))


if __name__ == "__main__":
    main()
