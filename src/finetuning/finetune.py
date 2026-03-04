import unsloth
from unsloth import FastLanguageModel
import json
import gc
import random
import numpy as np
import torch
import wandb
from pathlib import Path
from datasets import Dataset
from transformers import TrainingArguments, TrainerCallback
from unsloth import UnslothTrainer
from unsloth.chat_templates import get_chat_template

# ============================================================
# SECTION 1: CONSTANTS
# ============================================================
MAX_SEQ_LENGTH = 8192
DTYPE = None
LOAD_IN_4BIT = True
LOAD_IN_8BIT = False
SAVE_BASE = "D:/MyLLMs"
DATASET_PATH = "./datasets/dataset_20260218_045534.json"
DATASET_NAME = "dataset_20260218_045534"

# ============================================================
# SECTION 2: TOOL DEFINITIONS (for chat template)
# ============================================================
import httpx
from typing import Dict, Any

SIM_API_URL = "http://127.0.0.1:8001"

async def move_to(pos: str = "") -> None:
    """
    Move the robot to the specified position.

    Args:
        pos: name of the target position
    """
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        resp = await client.post("/robot/move_to", params={"position": pos})
        resp.raise_for_status()
    print(f'Tool calling: move_to')

async def open_gripper() -> None:
    """
    Open the gripper. Make sure it isn't already open.

    """
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        resp = await client.post("/robot/open_gripper")
        resp.raise_for_status()
    print(f'Tool calling: open_gripper')


async def close_gripper() -> str:
    """
    Close the gripper. Make sure it is open first.

    Returns:
        return_status: status message if the gripping was successfull

    """
    mode = ""
    status = "OK"
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        try:
            resp = await client.post("/robot/close_gripper", params={"mode": mode})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = "ERROR"
    print(f'Tool calling: close_gripper')
    return status


async def locate_shapes() -> Dict[str, str]:
    """
    Detects shapes and updates their positions to exact ones for picking.
    Make sure you are in appropriate position where the shapes can be detected from.

    Returns:
        return_detected_shapes: detected shapes with their locations, empty locations will not be returned
    """
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        resp = await client.get("/robot/locate_shapes")
        resp.raise_for_status()
        results = resp.json()

    print(f'Tool calling: locate_shapes')
    return results


async def get_status() -> Any:
    """
    Get the current robot status: position and gripper state (open/closed).

    Returns:
        return_robot_position: the current robot position name
        return_gripper_oopen: if the gripper is open or closed, True or 1 for open, False or 0 for closed
    """
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        resp = await client.get("/robot/status")
        resp.raise_for_status()
        results = resp.json()

    return (results['gripper_open'], results['position']["name"])


async def get_positions() -> list[str]:
    """
    Get the full list of available positions where the robot can go.

    Returns:
        return_positions: list of names of avaliale positions, without unit, defaults to []

    """
    async with httpx.AsyncClient(base_url=SIM_API_URL, timeout=30) as client:
        resp = await client.get("/scene/get_state")
        resp.raise_for_status()
        results = resp.json()

    message = "No positions available."
    if results and "positions" in results:
        resp = [position for position in results["positions"].keys()]
    print(f"Tool calling: get_positions.")
    return resp

tools = [move_to, open_gripper, close_gripper, get_positions, get_status, locate_shapes]

# ============================================================
# SECTION 3: CHAT TEMPLATE
# ============================================================
llama31_cot_template = \
"""{{- bos_token }}
{%- if custom_tools is defined %}
    {%- set tools = custom_tools %}
{%- endif %}
{%- if not tools_in_user_message is defined %}
    {%- set tools_in_user_message = true %}
{%- endif %}
{%- if not date_string is defined %}
    {%- set date_string = "26 July 2024" %}
{%- endif %}
{%- if not tools is defined %}
    {%- set tools = none %}
{%- endif %}

{#- This block extracts the system message #}
{%- if messages[0]['role'] == 'system' %}
    {%- set system_message = messages[0]['content'] %}
    {%- set messages = messages[1:] %}
{%- else %}
    {%- set system_message = "" %}
{%- endif %}

{#- System message + builtin tools #}
{{- "<|start_header_id|>system<|end_header_id|>\n\n" }}
{%- if builtin_tools is defined or tools is not none %}
    {{- "Environment: ipython\n" }}
{%- endif %}
{%- if builtin_tools is defined %}
    {{- "Tools: " + builtin_tools | reject('equalto', 'code_interpreter') | join(", ") + "\n\n"}}
{%- endif %}
{{- "Cutting Knowledge Date: December 2023\n" }}
{{- "Today Date: " + date_string + "\n\n" }}
{%- if tools is not none and not tools_in_user_message %}
    {{- "You have access to the following functions. To call a function, please respond with JSON for a function call." }}
    {{- 'Respond in the format {"name": function name, "parameters": dictionary of argument name and its value}.' }}
    {{- "Do not use variables.\n\n" }}
    {%- for t in tools %}
        {{- t | tojson(indent=4) }}
        {{- "\n\n" }}
    {%- endfor %}
{%- endif %}
{{- system_message }}
{{- "<|eot_id|>" }}

{#- Custom tools in user message #}
{%- if tools_in_user_message and not tools is none %}
    {%- if messages | length != 0 %}
        {%- set first_user_message = messages[0]['content'] %}
        {%- set messages = messages[1:] %}
    {%- else %}
        {{- raise_exception("Cannot put tools in the first user message when there's no first user message!") }}
    {%- endif %}
    {{- '<|start_header_id|>user<|end_header_id|>\n\n' -}}
    {{- "Given the following functions, please respond with a JSON for a function call " }}
    {{- "with its proper arguments that best answers the given prompt.\n\n" }}
    {{- 'Respond in the format {"name": function name, "parameters": dictionary of argument name and its value}.' }}
    {{- "Do not use variables.\n\n" }}
    {%- for t in tools %}
        {{- t | tojson(indent=4) }}
        {{- "\n\n" }}
    {%- endfor %}
    {{- first_user_message + "<|eot_id|>"}}
{%- endif %}

{%- for message in messages %}
    {%- if not (message.role == 'ipython' or message.role == 'tool' or 'tool_calls' in message) %}
        {{- '<|start_header_id|>' + message['role'] + '<|end_header_id|>\n\n'+ message['content'] + '<|eot_id|>' }}
    {%- elif 'tool_calls' in message %}
        {%- if not message.tool_calls|length == 1 %}
            {{- raise_exception("This model only supports single tool-calls at once!") }}
        {%- endif %}
        {%- set tool_call = message.tool_calls[0].function %}
        {%- if builtin_tools is defined and tool_call.name in builtin_tools %}
            {{- '<|start_header_id|>assistant<|end_header_id|>\n\n' -}}
            {%- if message.content is defined and message.content %}
                {{- message.content + "\n" }}
            {%- endif %}
            {{- "<|python_tag|>" + tool_call.name + ".call(" }}
            {%- for arg_name, arg_val in tool_call.arguments | items %}
                {{- arg_name + '="' + arg_val + '"' }}
                {%- if not loop.last %}
                    {{- ", " }}
                {%- endif %}
                {%- endfor %}
            {{- ")" }}
        {%- else  %}
            {{- '<|start_header_id|>assistant<|end_header_id|>\n\n' -}}

            {#- THE FIX: Render content (thought) before tool call -#}
            {%- if message.content is defined and message.content %}
                {{- message.content + "\n" }}
            {%- endif %}

            {{- '{"name": "' + tool_call.name + '", ' }}
            {{- '"parameters": ' }}
            {{- tool_call.arguments | tojson }}
            {{- "}" }}
        {%- endif %}
        {%- if builtin_tools is defined %}
            {{- "<|eom_id|>" }}
        {%- else %}
            {{- "<|eot_id|>" }}
        {%- endif %}
    {%- elif message.role == "tool" or message.role == "ipython" %}
        {{- "<|start_header_id|>ipython<|end_header_id|>\n\n" }}
        {%- if message.content is mapping or message.content is iterable %}
            {{- message.content | tojson }}
        {%- else %}
            {{- message.content }}
        {%- endif %}
        {{- "<|eot_id|>" }}
    {%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
    {{- '<|start_header_id|>assistant<|end_header_id|>\n\n' }}
{%- endif %}
"""

# ============================================================
# SECTION 4: DATASET LOADING AND 4-WAY SPLIT
# ============================================================
with open(DATASET_PATH) as f:
    raw_dataset = json.load(f)

EVAL_SCENES = {
    "scene_bay_A_cylinder_red",
    "scene_BIN_RED_LEFT_cable",
    "scene_binA_001_gear",
}

# Seen tasks: 1.x-11.x and 13.x
# Unseen tasks: 12.x, 14.x, 15.x
train_conversations = []
eval_unseen_scenes_seen_tasks = []
eval_seen_scenes_unseen_tasks = []
eval_unseen_scenes_unseen_tasks = []

for item in raw_dataset:
    scene_id = item["metadata"]["scene_id"]
    draft_id = item["metadata"]["draft_id"]
    major = int(draft_id.split(".")[0])

    is_eval_scene = scene_id in EVAL_SCENES
    is_unseen_task = major >= 12 and major != 13

    if not is_unseen_task and is_eval_scene:
        eval_unseen_scenes_seen_tasks.append(item["messages"])
    elif is_unseen_task and not is_eval_scene:
        eval_seen_scenes_unseen_tasks.append(item["messages"])
    elif is_unseen_task and is_eval_scene:
        eval_unseen_scenes_unseen_tasks.append(item["messages"])
    else:
        train_conversations.append(item["messages"])

# Cap eval datasets at 100 examples with fixed seed
EVAL_CAP = 100
rng = random.Random(42)

def cap_and_shuffle(conversations, cap):
    if len(conversations) > cap:
        return rng.sample(conversations, cap)
    return conversations

eval_unseen_scenes_seen_tasks = cap_and_shuffle(eval_unseen_scenes_seen_tasks, EVAL_CAP)
eval_seen_scenes_unseen_tasks = cap_and_shuffle(eval_seen_scenes_unseen_tasks, EVAL_CAP)
eval_unseen_scenes_unseen_tasks = cap_and_shuffle(eval_unseen_scenes_unseen_tasks, EVAL_CAP)

# Save eval datasets to disk for reproducibility
datasets_dir = Path(__file__).parent / "datasets"
for name, convos in [
    ("unseen_scenes_seen_tasks", eval_unseen_scenes_seen_tasks),
    ("seen_scenes_unseen_tasks", eval_seen_scenes_unseen_tasks),
    ("unseen_scenes_unseen_tasks", eval_unseen_scenes_unseen_tasks),
]:
    out_path = datasets_dir / f"{DATASET_NAME}_{name}.json"
    with open(out_path, "w") as f:
        json.dump([{"messages": c} for c in convos], f, indent=2)
    print(f"Saved eval dataset '{name}' ({len(convos)} examples) to {out_path}")

raw_train_dataset = Dataset.from_dict({"messages": train_conversations})
raw_eval_datasets = {
    "unseen_scenes_seen_tasks": Dataset.from_dict({"messages": eval_unseen_scenes_seen_tasks}),
    "seen_scenes_unseen_tasks": Dataset.from_dict({"messages": eval_seen_scenes_unseen_tasks}),
    "unseen_scenes_unseen_tasks": Dataset.from_dict({"messages": eval_unseen_scenes_unseen_tasks}),
}

print(f"\nTraining samples: {len(raw_train_dataset)}")
for name, ds in raw_eval_datasets.items():
    print(f"Eval '{name}': {len(ds)}")

# ============================================================
# SECTION 5: HELPER FUNCTIONS
# ============================================================
with open('instruction_message.txt') as f:
    instruction_message = f.read()


def clean_conversation(convo):
    """Clean a conversation by fixing null values and arguments."""
    for msg in convo:
        if msg.get("content") is None:
            msg["content"] = ""
        if "tool_calls" in msg and msg["tool_calls"] is None:
            del msg["tool_calls"]
        if msg.get("tool_calls"):
            for tool in msg["tool_calls"]:
                if "function" in tool:
                    args = tool["function"].get("arguments")
                    if args is None:
                        tool["function"]["arguments"] = {}
                    elif isinstance(args, dict):
                        clean_args = {k: v for k, v in args.items() if v is not None}
                        tool["function"]["arguments"] = clean_args
    return convo


def make_formatting_func(tok, tool_list, instr_message, max_seq_len):
    """Factory that returns a formatting function bound to the given tokenizer."""
    def formatting_prompts_func(examples):
        convos = examples["messages"]
        all_input_ids = []
        all_attention_mask = []
        all_labels = []

        system_part = {"role": "system", "content": instr_message}

        for convo in convos:
            new_convo = [system_part] + convo
            new_convo = clean_conversation(new_convo)

            full_text = tok.apply_chat_template(
                new_convo,
                tokenize=False,
                add_generation_prompt=False,
                tools=tool_list
            )

            full_tokens = tok(
                full_text,
                truncation=True,
                max_length=max_seq_len,
                return_tensors=None
            )

            labels = [-100] * len(full_tokens["input_ids"])

            for i, msg in enumerate(new_convo):
                if msg.get("role") != "assistant":
                    continue

                prefix_text = tok.apply_chat_template(
                    new_convo[:i],
                    tokenize=False,
                    add_generation_prompt=True,
                    tools=tool_list
                )
                start_idx = len(tok(
                    prefix_text,
                    truncation=True,
                    max_length=max_seq_len,
                    return_tensors=None
                )["input_ids"])

                prefix_with_text = tok.apply_chat_template(
                    new_convo[:i + 1],
                    tokenize=False,
                    add_generation_prompt=False,
                    tools=tool_list
                )
                end_idx = len(tok(
                    prefix_with_text,
                    truncation=True,
                    max_length=max_seq_len,
                    return_tensors=None
                )["input_ids"])

                for j in range(start_idx, min(end_idx, len(labels))):
                    labels[j] = full_tokens["input_ids"][j]

            all_input_ids.append(full_tokens["input_ids"])
            all_attention_mask.append(full_tokens["attention_mask"])
            all_labels.append(labels)

        return {
            "input_ids": all_input_ids,
            "attention_mask": all_attention_mask,
            "labels": all_labels
        }
    return formatting_prompts_func


def preprocess_logits_for_metrics(logits, labels):
    if isinstance(logits, tuple):
        logits = logits[0]
    result = logits.argmax(dim=-1)
    del logits
    return result


def compute_metrics(eval_preds):
    preds, labels = eval_preds
    # Shift alignment: logits[i] predicts token at position i+1
    preds = preds[:, :-1]
    labels = labels[:, 1:]
    mask = labels != -100
    active_preds = preds[mask]
    active_labels = labels[mask]
    accuracy = (active_preds == active_labels).mean()
    return {"accuracy": float(accuracy)}


class SaveAdapterCallback(TrainerCallback):
    """Saves LoRA adapters at each epoch boundary."""
    def __init__(self, model, tokenizer, save_base, name_template):
        self.model = model
        self.tokenizer = tokenizer
        self.save_base = save_base
        self.name_template = name_template

    def on_epoch_end(self, args, state, control, **kwargs):
        epoch = int(state.epoch)
        save_dir = f"{self.save_base}/{self.name_template.format(ep=epoch)}"
        self.model.save_pretrained(save_dir)
        self.tokenizer.save_pretrained(save_dir)
        print(f"Saved adapter checkpoint to {save_dir}")


class ClearCacheCallback(TrainerCallback):
    """Clears CPU and GPU caches after evaluation to prevent
    memory fragmentation that degrades training throughput."""
    def on_evaluate(self, args, state, control, **kwargs):
        gc.collect()
        torch.cuda.empty_cache()


def make_short_name(model_name):
    """'Llama-3.2-3B-Instruct-unsloth-bnb-4bit' -> 'Llama-3.2-3B'"""
    name = model_name
    for suffix in ["-Instruct-unsloth-bnb-4bit", "-Instruct", "-unsloth-bnb-4bit"]:
        name = name.replace(suffix, "")
    return name


def make_run_name(short_name, r, alpha, lr, lr_method, num_epochs):
    return f"{short_name}_r{r}_a{alpha}_lr{lr:.0e}_{lr_method}_ep{num_epochs}"


# ============================================================
# SECTION 6: TRAINING FUNCTION
# ============================================================
def run_training(model_name, r, alpha, lr, lr_method, num_epochs, save_adapter_per_epoch=False):
    """Single training run. Handles model loading, tokenization, training, saving, and cleanup."""
    short_name = make_short_name(model_name)
    run_name = make_run_name(short_name, r, alpha, lr, lr_method, num_epochs)
    save_dir = f"{SAVE_BASE}/{run_name}"

    print(f"\n{'='*60}")
    print(f"Starting run: {run_name}")
    print(f"{'='*60}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=f"unsloth/{model_name}",
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=DTYPE,
        load_in_4bit=LOAD_IN_4BIT,
        load_in_8bit=LOAD_IN_8BIT,
        full_finetuning=False,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=alpha * r,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        use_rslora=False,
        loftq_config=None,
    )

    tokenizer = get_chat_template(tokenizer, chat_template="llama-3.2")
    tokenizer.chat_template = llama31_cot_template

    formatting_func = make_formatting_func(tokenizer, tools, instruction_message, MAX_SEQ_LENGTH)
    tok_train = raw_train_dataset.map(formatting_func, batched=True, keep_in_memory=True)
    tok_evals = {k: v.map(formatting_func, batched=True, keep_in_memory=True) for k, v in raw_eval_datasets.items()}

    callbacks = [ClearCacheCallback()]
    if save_adapter_per_epoch:
        name_template = make_run_name(short_name, r, alpha, lr, lr_method, "{ep}")
        callbacks.append(SaveAdapterCallback(model, tokenizer, SAVE_BASE, name_template))

    wandb.init(
        project="Finetuning robot agent",
        name=run_name,
        config={
            "model_name": model_name,
            "short_name": short_name,
            "r": r,
            "lora_alpha": alpha * r,
            "alpha_multiplier": alpha,
            "learning_rate": lr,
            "lr_scheduler_type": lr_method,
            "num_train_epochs": num_epochs,
            "dataset": DATASET_NAME,
            "dataset_path": DATASET_PATH,
            "train_samples": len(tok_train),
            "eval_unseen_scenes_seen_tasks_samples": len(tok_evals["unseen_scenes_seen_tasks"]),
            "eval_seen_scenes_unseen_tasks_samples": len(tok_evals["seen_scenes_unseen_tasks"]),
            "eval_unseen_scenes_unseen_tasks_samples": len(tok_evals["unseen_scenes_unseen_tasks"]),
            "max_seq_length": MAX_SEQ_LENGTH,
        },
    )

    training_args = TrainingArguments(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=20,
        num_train_epochs=num_epochs,
        learning_rate=lr,
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0,
        lr_scheduler_type=lr_method,
        seed=3407,
        output_dir=f"{SAVE_BASE}/checkpoints/{run_name}",
        save_strategy="no",
        report_to="wandb",
        gradient_checkpointing=True
    )
    wandb.config.update(training_args.to_dict(), allow_val_change=True)

    trainer = UnslothTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=tok_train,
        eval_dataset=tok_evals,
        max_seq_length=MAX_SEQ_LENGTH,
        packing=False,
        compute_metrics=compute_metrics,
        preprocess_logits_for_metrics=preprocess_logits_for_metrics,
        callbacks=callbacks,
        args=training_args,
    )

    trainer.train()

    if not save_adapter_per_epoch:
        model.save_pretrained(save_dir)
        tokenizer.save_pretrained(save_dir)

    wandb.finish()

    del model, trainer, tok_train, tok_evals
    gc.collect()
    torch.cuda.empty_cache()


# ============================================================
# SECTION 7: CLI ENTRY POINT
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fine-tune a single model configuration")
    parser.add_argument("--model-name", type=str, required=True)
    parser.add_argument("--r", type=int, required=True)
    parser.add_argument("--alpha", type=int, required=True)
    parser.add_argument("--lr", type=float, required=True)
    parser.add_argument("--lr-method", type=str, required=True)
    parser.add_argument("--num-epochs", type=int, required=True)
    parser.add_argument("--save-adapter-per-epoch", action="store_true")
    args = parser.parse_args()

    run_training(
        model_name=args.model_name,
        r=args.r,
        alpha=args.alpha,
        lr=args.lr,
        lr_method=args.lr_method,
        num_epochs=args.num_epochs,
        save_adapter_per_epoch=args.save_adapter_per_epoch,
    )
