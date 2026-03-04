"""Grid search wrapper that launches each training run as a subprocess
for clean VRAM isolation between runs."""

import subprocess
import sys
from itertools import product
from pathlib import Path

MODEL_NAMES = ["Llama-3.2-3B-Instruct-unsloth-bnb-4bit"]
R_VALUES = [32, 64, 128]
ALPHA_VALUES = [1, 2]
LR_VALUES = [2e-4, 6e-5]
LR_METHODS = ["cosine", "constant_with_warmup"]
NUM_EPOCHS_LIST = [1, 2, 3]

FINETUNE_SCRIPT = "finetune.py"
SAVE_BASE = Path("D:/MyLLMs")


def make_short_name(model_name):
    """'Llama-3.2-3B-Instruct-unsloth-bnb-4bit' -> 'Llama-3.2-3B'"""
    name = model_name
    for suffix in ["-Instruct-unsloth-bnb-4bit", "-Instruct", "-unsloth-bnb-4bit"]:
        name = name.replace(suffix, "")
    return name


def make_run_name(short_name, r, alpha, lr, lr_method, num_epochs):
    return f"{short_name}_r{r}_a{alpha}_lr{lr:.0e}_{lr_method}_ep{num_epochs}"


def run_exists(model_name, r, alpha, lr, lr_method):
    """Check if all expected adapters for this config already exist on disk."""
    short_name = make_short_name(model_name)
    if lr_method == "constant_with_warmup":
        # All epoch dirs must exist (they're all produced by a single run)
        return all(
            (SAVE_BASE / make_run_name(short_name, r, alpha, lr, lr_method, ep)).is_dir()
            for ep in NUM_EPOCHS_LIST
        )
    else:
        # Single adapter dir for this specific epoch count — checked per-run
        return None  # handled per-epoch in build_commands


def build_commands():
    """Generate all (command, run_name) pairs for the grid search,
    skipping runs whose adapters already exist."""
    commands = []
    for model_name, r, alpha, lr, lr_method in product(
        MODEL_NAMES, R_VALUES, ALPHA_VALUES, LR_VALUES, LR_METHODS
    ):
        short_name = make_short_name(model_name)
        if lr_method == "constant_with_warmup":
            max_ep = max(NUM_EPOCHS_LIST)
            if run_exists(model_name, r, alpha, lr, lr_method):
                display_name = make_run_name(short_name, r, alpha, lr, lr_method, max_ep)
                print(f"SKIP (all epochs exist): {display_name}")
                continue
            cmd = [
                sys.executable, FINETUNE_SCRIPT,
                "--model-name", model_name,
                "--r", str(r),
                "--alpha", str(alpha),
                "--lr", str(lr),
                "--lr-method", lr_method,
                "--num-epochs", str(max_ep),
                "--save-adapter-per-epoch",
            ]
            run_name = make_run_name(short_name, r, alpha, lr, lr_method, max_ep)
            commands.append((cmd, run_name))
        else:
            for num_epochs in NUM_EPOCHS_LIST:
                run_name = make_run_name(short_name, r, alpha, lr, lr_method, num_epochs)
                if (SAVE_BASE / run_name).is_dir():
                    print(f"SKIP (exists): {run_name}")
                    continue
                cmd = [
                    sys.executable, FINETUNE_SCRIPT,
                    "--model-name", model_name,
                    "--r", str(r),
                    "--alpha", str(alpha),
                    "--lr", str(lr),
                    "--lr-method", lr_method,
                    "--num-epochs", str(num_epochs),
                ]
                commands.append((cmd, run_name))
    return commands


if __name__ == "__main__":
    commands = build_commands()
    total = len(commands)
    print(f"\nGrid search: {total} runs remaining\n")

    for i, (cmd, run_name) in enumerate(commands, 1):
        print(f"[{i}/{total}] Launching: {run_name}")
        result = subprocess.run(cmd, cwd=sys.path[0] or ".")
        if result.returncode != 0:
            print(f"[{i}/{total}] FAILED (exit code {result.returncode}): {run_name}")
        else:
            print(f"[{i}/{total}] Completed: {run_name}")
        print()

    print("Grid search finished.")
