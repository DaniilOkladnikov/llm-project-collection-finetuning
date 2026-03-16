"""Convert a merged HuggingFace model to GGUF using llama.cpp's convert_hf_to_gguf.py."""

import argparse
import subprocess
import sys
from pathlib import Path

MERGED_MODEL = Path("D:/MyLLMs/merged/Llama-3.2-3B_r64_a2_lr2e-04_constant_with_warmup_ep2_16bit")
GGUF_DIR = Path("D:/MyLLMs/gguf")
CONVERT_SCRIPT = Path("C:/Users/okladnik/Documents/llama.cpp/convert_hf_to_gguf.py")

# Supported by convert_hf_to_gguf.py without a separate quantize binary
QUANT_METHODS = ["f16", "bf16", "f32", "q8_0", "auto"]


def save_gguf(model_path: Path, output_dir: Path, quant_method: str):
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = model_path.name
    out_file = output_dir / f"{stem}_{quant_method}.gguf"

    if out_file.exists():
        print(f"Output already exists: {out_file} — skipping")
        return

    cmd = [
        sys.executable,
        str(CONVERT_SCRIPT),
        str(model_path),
        "--outfile", str(out_file),
        "--outtype", quant_method,
    ]

    print(f"Converting {model_path.name} -> {out_file.name} ({quant_method}) ...")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"Conversion failed (exit code {result.returncode})")
        sys.exit(result.returncode)

    print(f"\nDone: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Save merged model as GGUF via llama.cpp")
    parser.add_argument(
        "--model",
        type=Path,
        default=MERGED_MODEL,
        help="Path to the merged HF model directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=GGUF_DIR,
        help="Directory to write the GGUF file (default: D:/MyLLMs/gguf)",
    )
    parser.add_argument(
        "--quant",
        type=str,
        default="q8_0",
        choices=QUANT_METHODS,
        help="Output type (default: q8_0). f16/bf16/f32/q8_0/auto supported without a quantize binary.",
    )
    args = parser.parse_args()

    save_gguf(args.model, args.output_dir, args.quant)


if __name__ == "__main__":
    main()
