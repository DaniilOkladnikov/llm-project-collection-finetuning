"""Merge a LoRA adapter into its base model and save as a standard HuggingFace model.

Runs as a subprocess for VRAM isolation — process exit frees all GPU memory.

Usage:
    python merge_adapter.py <adapter_path> <output_path>
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument("adapter_path", type=Path, help="Path to LoRA adapter directory")
    parser.add_argument("output_path", type=Path, help="Directory to write merged HF model")
    args = parser.parse_args()

    if not args.adapter_path.exists():
        print(f"Adapter path does not exist: {args.adapter_path}")
        sys.exit(1)

    from unsloth import FastLanguageModel

    print(f"Loading adapter: {args.adapter_path}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.adapter_path),
        max_seq_length=8192,
        dtype=None,
        load_in_4bit=False,
        load_in_8bit=False,
    )

    print(f"Merging and saving to: {args.output_path}")
    model.save_pretrained_merged(
        str(args.output_path), tokenizer, save_method="merged_16bit",
    )

    print("Merge complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
