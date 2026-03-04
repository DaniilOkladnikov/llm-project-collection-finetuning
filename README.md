# LLM Finetuning — Robot Agent

Fine-tunes LLaMA models (via [Unsloth](https://github.com/unslothai/unsloth)) to control a robot arm using tool calls. Tracks experiments with Weights & Biases.

## Runnable Scripts

### 1. Generate dataset

Runs scenario drafts across all scene configs and saves a timestamped JSON to `src/finetuning/datasets/`.

```bash
uv run src/finetuning/generate_dataset.py
```

### 2. Single training run

Fine-tunes one model configuration. Saves the LoRA adapter to `D:/MyLLMs/<run_name>/`.

```bash
uv run src/finetuning/finetune.py \
  --model-name Llama-3.2-3B-Instruct-unsloth-bnb-4bit \
  --r 32 \
  --alpha 1 \
  --lr 2e-4 \
  --lr-method cosine \
  --num-epochs 3
```

Add `--save-adapter-per-epoch` to checkpoint after each epoch instead of only at the end.

### 3. Hyperparameter grid search

Iterates over all combinations defined in `run_grid.py`, launching `finetune.py` as a subprocess for clean VRAM isolation. Skips runs whose output directories already exist.

```bash
uv run src/finetuning/run_grid.py
```

Edit `MODEL_NAMES`, `R_VALUES`, `ALPHA_VALUES`, `LR_VALUES`, `LR_METHODS`, and `NUM_EPOCHS_LIST` at the top of the file to customize the grid.
