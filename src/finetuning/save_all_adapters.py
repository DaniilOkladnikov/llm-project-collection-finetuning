"""Save all LoRA adapters from D:/MyLLMs as permanent Ollama models.

For each adapter:
  1. Merge adapter with base model (subprocess for VRAM isolation)
  2. Generate Modelfile with custom Llama template
  3. Create Ollama model via `ollama create`
  4. Clean up merged temp dir and orphaned blobs

Resumable via save_all_adapters_progress.json.

Usage:
  cd src/finetuning
  python save_all_adapters.py
"""

import json
import logging
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
ADAPTERS_DIR = Path("D:/MyLLMs")
MERGED_TEMP_DIR = ADAPTERS_DIR / "_merged_temp"
TEMPLATE_PATH = Path(__file__).parent / "my_llama_template.txt"
MERGE_SCRIPT = Path(__file__).parent / "merge_adapter.py"
PROGRESS_FILE = Path(__file__).parent / "save_all_adapters_progress.json"

OLLAMA_EXE = Path("D:/Ollama/ollama.exe")
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODELS_DIR = Path("D:/OLLAMA_MODELS")

SKIP_PREFIXES = ("_", "models--")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


# ---------------------------------------------------------------------------
# Discover adapters
# ---------------------------------------------------------------------------
def discover_adapters() -> list[str]:
    """Return sorted list of adapter directory names in ADAPTERS_DIR."""
    adapters = []
    for entry in sorted(ADAPTERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        if not (entry / "adapter_config.json").exists():
            continue
        adapters.append(entry.name)
    return adapters


# ---------------------------------------------------------------------------
# Merge step (subprocess)
# ---------------------------------------------------------------------------
def merge_adapter(adapter_name: str) -> bool:
    """Merge adapter into MERGED_TEMP_DIR. Returns True on success."""
    adapter_path = str(ADAPTERS_DIR / adapter_name)
    output_path = str(MERGED_TEMP_DIR)

    if MERGED_TEMP_DIR.exists():
        shutil.rmtree(MERGED_TEMP_DIR)

    logging.info(f"  Merging {adapter_name} ...")
    result = subprocess.run(
        [sys.executable, str(MERGE_SCRIPT), adapter_path, output_path],
        timeout=600,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Ollama model management
# ---------------------------------------------------------------------------
def _ollama_env() -> dict:
    env = os.environ.copy()
    env["OLLAMA_HOST"] = OLLAMA_HOST
    return env


def create_ollama_model(model_name: str) -> bool:
    """Create a permanent Ollama model from the merged weights."""
    template_content = TEMPLATE_PATH.read_text(encoding="utf-8")

    modelfile_path = MERGED_TEMP_DIR / "Modelfile"
    merged_path = str(MERGED_TEMP_DIR).replace("\\", "/")
    modelfile_content = f'FROM {merged_path}\nTEMPLATE """{template_content}"""\n'
    modelfile_path.write_text(modelfile_content, encoding="utf-8")

    logging.info(f"  Creating Ollama model '{model_name}' ...")
    result = subprocess.run(
        [str(OLLAMA_EXE), "create", model_name, "-f", str(modelfile_path)],
        timeout=600,
        env=_ollama_env(),
    )
    return result.returncode == 0


def cleanup_orphaned_blobs():
    """Delete blob files not referenced by any remaining Ollama manifest."""
    manifests_dir = OLLAMA_MODELS_DIR / "manifests"
    blobs_dir = OLLAMA_MODELS_DIR / "blobs"

    if not blobs_dir.exists():
        return

    referenced = set()
    if manifests_dir.exists():
        for manifest_file in manifests_dir.rglob("*"):
            if not manifest_file.is_file():
                continue
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                if "config" in manifest and "digest" in manifest["config"]:
                    referenced.add(manifest["config"]["digest"])
                for layer in manifest.get("layers", []):
                    if "digest" in layer:
                        referenced.add(layer["digest"])
            except (json.JSONDecodeError, KeyError):
                continue

    referenced_filenames = {d.replace(":", "-") for d in referenced}

    removed = 0
    for blob in blobs_dir.iterdir():
        if blob.is_file() and blob.name not in referenced_filenames:
            size_mb = blob.stat().st_size / (1024 * 1024)
            blob.unlink()
            removed += 1
            logging.info(f"    Removed orphaned blob {blob.name} ({size_mb:.0f} MB)")

    if removed:
        logging.info(f"    Cleaned up {removed} orphaned blob(s)")


def cleanup_merged_dir():
    if MERGED_TEMP_DIR.exists():
        logging.info("  Removing merged temp dir ...")
        shutil.rmtree(MERGED_TEMP_DIR)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    adapters = discover_adapters()
    progress = load_progress()

    pending = [a for a in adapters if progress.get(a) != "complete"]
    if len(pending) > 20:
        pending = random.sample(pending, 1)
    pending = ["Llama-3.2-3B_r64_a2_lr6e-05_constant_with_warmup_ep2"]
    total = len(pending)

    logging.info(f"Found {len(adapters)} adapters, {total} remaining\n")

    for i, adapter_name in enumerate(pending, 1):
        logging.info(f"[{i}/{total}] Processing: {adapter_name}")

        # 1. Merge
        if not merge_adapter(adapter_name):
            logging.error(f"[{i}/{total}] FAILED to merge: {adapter_name}")
            cleanup_merged_dir()
            continue

        # 2. Create Ollama model
        if not create_ollama_model(f"{adapter_name}-q16"):
            logging.error(f"[{i}/{total}] FAILED to create Ollama model: {adapter_name}")
            cleanup_merged_dir()
            continue

        # 3. Cleanup
        cleanup_merged_dir()
        #cleanup_orphaned_blobs()

        # 4. Record success
        progress[adapter_name] = "complete"
        save_progress(progress)
        logging.info(f"[{i}/{total}] Done: {adapter_name}\n")

    logging.info("All adapters processed.")


if __name__ == "__main__":
    main()
