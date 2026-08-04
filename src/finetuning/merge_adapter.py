"""Merge a LoRA adapter into its base model and save as a standard HuggingFace model.

Runs as a subprocess for VRAM isolation — process exit frees all GPU memory.

Usage:
    python merge_adapter.py <adapter_path> <output_path>
"""

import os
# Same two env vars finetune.py sets, for the same reasons -- this script loads
# through the identical unsloth path, so it inherits the identical problems.
# unsloth_zoo turns on hf_transfer unless this is already set; its Rust
# downloader leaks file handles on Windows and dies mid-shard.
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
# No MSVC (cl.exe) on this machine, so TorchInductor can't build the C++ kernels
# unsloth generates for its torch.compile'd ops. Must be set before `import
# unsloth` -- unsloth_zoo reads it at import time.
os.environ["UNSLOTH_COMPILE_DISABLE"] = "1"

import argparse
import json
import sys
import traceback
from pathlib import Path


def is_gpt_oss_adapter(adapter_path: Path) -> bool:
    """Whether this adapter was trained on a gpt-oss base. Family detection by the
    base model recorded in adapter_config.json rather than the adapter dir name,
    since that name is only a convention of the training script."""
    config = adapter_path / "adapter_config.json"
    if not config.exists():
        return False
    base = json.loads(config.read_text()).get("base_model_name_or_path") or ""
    return "gpt-oss" in base.lower()


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument("adapter_path", type=Path, help="Path to LoRA adapter directory")
    parser.add_argument("output_path", type=Path, help="Directory to write merged HF model")
    args = parser.parse_args()

    if not args.adapter_path.exists():
        print(f"Adapter path does not exist: {args.adapter_path}")
        sys.exit(1)

    from unsloth import FastLanguageModel

    is_gpt_oss = is_gpt_oss_adapter(args.adapter_path)

    # gpt-oss is loaded in 4bit, everything else in 16bit. The merge itself does
    # not care: unsloth streams the base weights straight off the checkpoint on
    # disk and only reads the LoRA tensors out of the loaded model, so this
    # choice sets the loading cost and nothing about the merged output. For
    # gpt-oss the 16bit route is the expensive wrong answer -- its 16bit repo is
    # MXFP4, and loading that means either dequantizing to a ~42GB bf16 model
    # (more than this box's free RAM, and the dequantize stages int64 scratch on
    # the GPU that does not fit alongside the weights either) or taking the
    # native MXFP4 path, which imports the `kernels` package -- not installed,
    # and its hub kernels have no Windows build. 4bit loads the same
    # bnb-quantized base the adapter was trained on, in ~12GB.
    print(f"Loading adapter: {args.adapter_path}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.adapter_path),
        max_seq_length=8192,
        dtype=None,
        load_in_4bit=is_gpt_oss,
        load_in_8bit=False,
    )

    # gpt-oss must be merged as mxfp4, which keeps the base checkpoint's packed
    # expert tensors and only rewrites what LoRA touched. "merged_16bit" makes
    # unsloth dequantize every expert to bf16 while assembling a shard in memory,
    # which MemoryErrors here -- and would be pointless anyway, since
    # save_adapters_gguf.py converts gpt-oss with --outtype mxfp4. The
    # save_pretrained_merged entry point unsloth binds to a PeftModel does not
    # apply the gpt-oss override its other save path has, so pass it explicitly.
    save_method = "mxfp4" if is_gpt_oss else "merged_16bit"

    print(f"Merging and saving to: {args.output_path} (save_method={save_method})")
    model.save_pretrained_merged(
        str(args.output_path), tokenizer, save_method=save_method,
    )

    print("Merge complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Full traceback, not just str(e) -- this runs as a subprocess, so a bare
        # message is all the parent gets and it is rarely enough to locate the
        # failure inside the unsloth/transformers loading stack.
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
