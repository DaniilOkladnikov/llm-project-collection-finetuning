"""Merge all LoRA adapters into base model and convert to GGUF (q8_0).

For each adapter:
  1. Skip if q8_0 GGUF already exists in output directory
  2. Merge adapter with base model via subprocess (VRAM isolation)
  3. Convert merged model to q8_0 GGUF using llama.cpp's convert_hf_to_gguf.py
  4. Clean up temporary merged model directory
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ADAPTERS_DIR = Path("D:/MyLLMs/adapters")
GGUF_DIR = Path("D:/MyLLMs/gguf")
MERGED_TEMP_DIR = Path("D:/MyLLMs/_merged_temp")
CONVERT_SCRIPT = Path("C:/Users/okladnik/Documents/llama.cpp/convert_hf_to_gguf.py")
MERGE_SCRIPT = Path(__file__).parent / "merge_adapter.py"
QUANT_METHOD = "q8_0"


def merge_adapter(adapter_path: Path, output_dir: Path) -> bool:
    """Merge LoRA adapter into base model via subprocess. Returns True on success."""
    if output_dir.exists():
        shutil.rmtree(output_dir)

    cmd = [
        sys.executable,
        str(MERGE_SCRIPT),
        str(adapter_path),
        str(output_dir),
    ]

    print(f"  Merging adapter -> {output_dir} ...")
    print(f"  Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=False, timeout=600)
    except subprocess.TimeoutExpired:
        print("  MERGE TIMED OUT\n")
        return False

    if result.returncode != 0:
        print(f"  MERGE FAILED (exit code {result.returncode})\n")
        return False

    print("  Merge complete.\n")
    return True


def convert_to_gguf(merged_model_path: Path, adapter_name: str,
                    output_dir: Path, quant_method: str) -> str:
    """Convert a merged HF model to GGUF. Returns 'ok', 'skipped', or 'failed'."""
    output_dir.mkdir(parents=True, exist_ok=True)

    out_file = output_dir / f"{adapter_name}_{quant_method}.gguf"

    if out_file.exists():
        print(f"  Already exists: {out_file.name} — skipping")
        return "skipped"

    cmd = [
        sys.executable,
        str(CONVERT_SCRIPT),
        str(merged_model_path),
        "--outfile", str(out_file),
        "--outtype", quant_method,
    ]

    print(f"  Converting -> {out_file.name} ({quant_method}) ...")
    print(f"  Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})\n")
        return "failed"

    print(f"  Done: {out_file.name}\n")
    return "ok"


def cleanup_merged_dir():
    if MERGED_TEMP_DIR.exists():
        print(f"  Cleaning up {MERGED_TEMP_DIR} ...")
        shutil.rmtree(MERGED_TEMP_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="Merge all LoRA adapters with base model and convert to q8_0 GGUF",
    )
    parser.add_argument(
        "--adapters-dir", type=Path, default=ADAPTERS_DIR,
        help="Directory containing LoRA adapter subdirectories",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=GGUF_DIR,
        help="Directory to write GGUF files",
    )
    parser.add_argument(
        "--filter", type=str, default="test_rand",
        help="Only process adapters whose name contains this substring",
    )
    args = parser.parse_args()

    adapters = sorted(
        p for p in args.adapters_dir.iterdir()
        if p.is_dir() and p.name != MERGED_TEMP_DIR.name
        and (p / "adapter_config.json").exists()
        and (args.filter is None or args.filter in p.name)
    )
    if not adapters:
        print(f"No adapter directories found in {args.adapters_dir}")
        sys.exit(1)

    print(f"Found {len(adapters)} adapters\n")

    ok = skipped = failed = 0
    for i, adapter in enumerate(adapters, 1):
        print(f"[{i}/{len(adapters)}] {adapter.name}")

        out_file = args.output_dir / f"{adapter.name}_{QUANT_METHOD}.gguf"
        if out_file.exists():
            print(f"  Already exists: {out_file.name} — skipping\n")
            skipped += 1
            continue

        # Phase 1: Merge adapter into base model
        if not merge_adapter(adapter, MERGED_TEMP_DIR):
            failed += 1
            cleanup_merged_dir()
            continue

        if not MERGED_TEMP_DIR.is_dir() or not any(MERGED_TEMP_DIR.iterdir()):
            print(f"  Merge reported success but {MERGED_TEMP_DIR} is missing or empty — skipping\n")
            failed += 1
            cleanup_merged_dir()
            continue

        # Phase 2: Convert merged model to q8_0 GGUF
        status = convert_to_gguf(MERGED_TEMP_DIR, adapter.name, args.output_dir, QUANT_METHOD)
        if status == "ok":
            ok += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

        # Phase 3: Cleanup
        cleanup_merged_dir()

    print(f"\nSummary: {ok} converted, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
