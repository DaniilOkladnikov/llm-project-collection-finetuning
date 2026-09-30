import os
os.environ["TORCHINDUCTOR_CACHE_DIR"] = "C:/tc"
os.environ["TRITON_CACHE_DIR"] = "C:/tc/triton"
# unsloth_zoo turns on hf_transfer unless this is already set. Its Rust
# downloader leaks file handles on Windows, so a hiccup mid-download leaves a
# locked .incomplete blob it then can't clean up (os error 32).
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
# No MSVC (cl.exe) on this machine, so TorchInductor can't build the C++ CPU
# kernels it generates for unsloth's torch.compile'd ops (e.g. swiglu). Turn
# unsloth's compilation into a no-op so everything runs eager. Must be set
# before `import unsloth` -- unsloth_zoo reads it at import time.
os.environ["UNSLOTH_COMPILE_DISABLE"] = "1"
# gpt-oss's attention sinks are served by unsloth's patch that replaces
# GptOssAttention.forward with a torch flex_attention path. With compilation
# disabled (above) there's no Triton flex kernel, so flex_attention falls back to
# torch's eager reference sdpa_dense_backward, which has a bf16 bug (softmax
# scores cast to bf16 while grad_out stays fp32 -> "expected scalar type Float
# but found BFloat16"). Setting this to "0" makes patch_GptOssAttention bail out
# (it early-returns on this flag), so transformers' own attention runs instead --
# and attn_implementation="eager" at load time selects its sink-aware eager path.
# Must be set before `import unsloth` so the temporary patch sees it. Only affects
# gpt-oss; other models don't use this patch.
os.environ["UNSLOTH_ENABLE_FLEX_ATTENTION"] = "0"
import unsloth
from unsloth import FastLanguageModel
import json
import gc
import random
from datetime import datetime
import torch
import wandb
from datasets import Dataset
from transformers import AutoProcessor, AutoTokenizer, TrainingArguments, TrainerCallback
from unsloth import UnslothTrainer
from unsloth.chat_templates import get_chat_template

# ============================================================
# SECTION 1: CONSTANTS
# ============================================================
# max_seq_length is measured from the dataset at startup (see
# build_train_dataset) so nothing is truncated and no context window is
# paid for that the data never uses.
DTYPE = None
LOAD_IN_4BIT = False
LOAD_IN_8BIT = True
SAVE_BASE = "D:/MyLLMs"
DATASET_PATH = "./datasets/dataset_2026-09-26_15-33-31.json"
DATASET_NAME = DATASET_PATH
# Any single record (one LLM invocation) that renders to more tokens than this
# is dropped on its own; the other records of its conversation are kept.
# Applied before anything else, including the max_seq_length measurement, so the
# context window is sized to what actually gets trained on.
MAX_CONTEXT_TOKENS = 3500
# Fraction of the surviving records to train on, sampled at random.
DATASET_FRACTION = 1
DATASET_SAMPLE_SEED = 12345

# Which modules LoRA attaches to, per family. Llama exposes all seven as plain
# nn.Linear, so a name list is enough.
LLAMA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"]
# gpt-oss has no gate_proj / up_proj / down_proj module anywhere -- its MLP is
# router + experts. In unsloth's bnb-4bit repo the experts are one submodule per
# expert, mlp.experts.gate_up_projs.0 ... .31 and mlp.experts.down_projs.0 ...
# .31, so the last path segment is the expert index and a name list can never
# match them (PEFT matches names on that last segment). Hence a regex, which
# PEFT re.fullmatch-es against the full module key.
GPT_OSS_TARGET_MODULES = (
    r".*\.(?:self_attn\.(?:q_proj|k_proj|v_proj|o_proj)"
    r"|mlp\.experts\.(?:gate_up_projs|down_projs)\.\d+)"
)

# ============================================================
# SECTION 2: TOOL DEFINITIONS (for chat template)
# ============================================================
import httpx
from typing import Dict, Any

SIM_API_URL = "http://127.0.0.1:8001"

async def move_robot_to(position: str) -> dict:
    """
    Move the robot to the specified position.

    Args:
        position: name of the target position

    Returns:
        {"status": "OK"/"ERROR", "content": null}
    """
    results = []
    return results

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


async def get_gripper_state() -> dict:
    """
    Get the gripper state.

    Returns:
        {"status": "OK"/"ERROR", "content": "open" or "closed"}
    """
    print("Tool calling: get_gripper_state")
    results = []
    return results

async def get_robot_position() -> dict:
    """
    Get the robot's current position.

    Returns:
        {"status": "OK"/"ERROR", "content": current position name}
    """
    results = []
    return results

async def list_avaliable_robot_positions() -> list[str]:
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

tools = [move_robot_to, open_gripper, close_gripper, list_avaliable_robot_positions, get_gripper_state, get_robot_position, locate_shapes]

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
# SECTION 4: DATASET LOADING
# ============================================================
# The dataset is a dict keyed by example index. Each entry is one LLM
# invocation: "input" holds the conversation so far, "output" the assistant
# text to produce. There are no tool messages -- "input" is a sequence of
# blocks separated by blank lines, each either a user message ("User: ...")
# or a DSL block emitted by the assistant (PROGRAM / MEMORY / RESOLUTION /
# TOOL CALL / TOOL RESULTS / ANSWER).
USER_PREFIX = "User:"


def parse_conversation(input_text, output_text):
    """Turn one {input, output} record into a chat message list.

    Each "User:" block becomes its own user message; runs of consecutive
    non-user blocks are merged back into one assistant message (they were a
    single invocation's output). "output" is appended as the final assistant
    message -- the only one trained on.
    """
    messages = []
    pending = []

    def flush():
        if pending:
            messages.append({"role": "assistant", "content": "\n\n".join(pending)})
            pending.clear()

    for block in input_text.split("\n\n"):
        if block.startswith(USER_PREFIX):
            flush()
            messages.append({"role": "user", "content": block[len(USER_PREFIX):].strip()})
        else:
            pending.append(block)
    flush()

    messages.append({"role": "assistant", "content": output_text})
    return messages


with open('instruction_message.txt') as f:
    instruction_message = f.read()


def build_train_dataset(tok, model_name):
    """Load the dataset, drop over-long records, sample, and measure.

    A record's context length is its length in tokens exactly as it is trained
    on (system message + tools + conversation so far + output, see
    render_example). Each record over
    MAX_CONTEXT_TOKENS is dropped on its own; every other record of its
    conversation is kept as long as it fits. Records are filtered
    independently, so which records of a conversation survive does not depend
    on the order they appear in.

    Returns (dataset, max_seq_length) where max_seq_length is the longest
    surviving sample, so nothing that gets trained on is truncated.
    """
    with open(DATASET_PATH) as f:
        raw_dataset = json.load(f)

    records = [item for _, item in sorted(raw_dataset.items(), key=lambda kv: int(kv[0]))]
    print(f"\nLoaded records: {len(records)}")

    lengths = []

    for r in records:
        convo = parse_conversation(r["input"], r["output"])
        prompt_ids, target_ids = tokenize_example(
            tok, model_name, convo, tools, instruction_message
        )
        lengths.append(len(prompt_ids) + len(target_ids))

    total_conversations = len({r["metadata"]["conversation_id"] for r in records})
    print(f"Token lengths over {len(lengths)} records: max={max(lengths)} "
          f"mean={sum(lengths) / len(lengths):.0f} min={min(lengths)}")

    kept = [(r, n) for r, n in zip(records, lengths) if n <= MAX_CONTEXT_TOKENS]
    affected_conversations = {
        r["metadata"]["conversation_id"]
        for r, n in zip(records, lengths) if n > MAX_CONTEXT_TOKENS
    }
    print(f"After dropping records over {MAX_CONTEXT_TOKENS} tokens: {len(kept)} records "
          f"({len(records) - len(kept)} removed, from "
          f"{len(affected_conversations)}/{total_conversations} conversations)")

    # Sample the fraction we train on. Shuffle first so the subset isn't biased by
    # the dataset's generation order (records arrive grouped by scene/task).
    rng = random.Random(DATASET_SAMPLE_SEED)
    rng.shuffle(kept)
    kept = kept[:int(len(kept) * DATASET_FRACTION)]
    print(f"After sampling {DATASET_FRACTION:.0%}: {len(kept)}")

    dataset = Dataset.from_dict({
        "messages": [parse_conversation(r["input"], r["output"]) for r, _ in kept]
    })
    max_seq_length = max(n for _, n in kept)
    print(f"\nTraining samples: {len(dataset)} (longest {max_seq_length} tokens)")
    return dataset, max_seq_length


# ============================================================
# SECTION 5: HELPER FUNCTIONS
# ============================================================
def is_llama_model(model_name):
    """Whether to use the Llama-specific setup, matched purely by name.

    Llama models get the project's hand-written llama31_cot_template forced on
    and the LOAD_IN_* (8-bit) load path. Every other model (e.g. gpt-oss) keeps
    the built-in chat template that ships with its tokenizer and loads in 4-bit.
    """
    return "llama" in model_name.lower()


def is_gpt_oss_model(model_name):
    """Whether this is a gpt-oss model, matched purely by name."""
    return "gpt-oss" in model_name.lower()


def is_gemma4_model(model_name):
    """Whether this is a Gemma 4 model, matched purely by name."""
    return "gemma-4" in model_name.lower()


def make_lora_kwargs(model_name):
    """The family-specific part of the get_peft_model call.

    Returned as kwargs rather than a fixed tuple because the three families need
    different arguments: the name-list families pass target_modules, while Gemma 4
    must pass none of it and select layers with unsloth's flags instead.

    gpt-oss forces target_parameters empty. Left at None, unsloth derives
    ["mlp.experts.gate_up_proj", "mlp.experts.down_proj"] from the MLP names in
    target_modules -- but those are the fused nn.Parameters of the *unquantized*
    model, which the bnb-4bit repo does not have. PEFT then matches nothing and
    warns, and unsloth rewrites that warning to say MoE experts are "handled
    separately", which they are not: runs before this trained attention only.
    """
    if is_gpt_oss_model(model_name):
        return {"target_modules": GPT_OSS_TARGET_MODULES, "target_parameters": []}
    if is_gemma4_model(model_name):
        # Gemma 4 gets unsloth's own recipe: target_modules and target_parameters
        # are deliberately left unset so get_peft_model derives them itself. A
        # hand-written name list breaks here because:
        #   1. Gemma4ClippableLinear wraps nn.Linear and PEFT cannot inject into it
        #      (huggingface/peft#3129); unsloth patches LoraModel._create_and_replace
        #      to redirect onto the inner .linear child, but only on this path.
        #   2. E2B carries both a vision and an audio encoder (vision_config and
        #      audio_config are both present) whose projections reuse the same
        #      q_proj/gate_proj names, so a bare list leaks LoRA into them. The
        #      flags below are what scope it to the language tower.
        # E2B itself is dense -- its config reports enable_moe_block=False, so the
        # Gemma4TextExperts path is dormant and the fused-nn.Parameter trap that
        # silently left gpt-oss's experts untrained does not apply. Leaving
        # target_parameters unset keeps that correct anyway if a genuinely MoE
        # Gemma 4 (26B-A4B) is ever added to the grid: unsloth then populates it
        # via get_moe_target_parameters instead of matching nothing.
        return {
            "finetune_language_layers":   True,
            "finetune_attention_modules": True,
            "finetune_mlp_modules":       True,
            "finetune_vision_layers":     False,
            "finetune_audio_layers":      False,
        }
    return {"target_modules": LLAMA_TARGET_MODULES, "target_parameters": None}


def as_tokenizer(obj):
    """Unwrap a multimodal processor into the tokenizer the rest of this file wants.

    Gemma 4 is a multimodal checkpoint, so AutoProcessor -- and unsloth's loader,
    which delegates multimodal architectures to FastModel -- hand back a processor
    rather than a tokenizer. Everything downstream calls tok(...),
    tok.apply_chat_template(...) and tok.save_pretrained(...), so unwrap to the
    inner tokenizer and carry the chat template across: on a multimodal repo the
    template ships with the processor, not with the tokenizer. A plain tokenizer
    passes through untouched.
    """
    tok = getattr(obj, "tokenizer", None)
    if tok is None:
        return obj
    if getattr(tok, "chat_template", None) is None:
        tok.chat_template = getattr(obj, "chat_template", None)
    return tok


def make_tokenizer(model_name):
    """Tokenizer with the project chat template, loaded without the model.

    Needed before FastLanguageModel.from_pretrained, which wants max_seq_length
    up front -- and that can only be measured by tokenizing the dataset.

    For Llama models the project's custom template is forced on; other models
    keep the built-in template that ships with their tokenizer.
    """
    if is_gemma4_model(model_name):
        return as_tokenizer(AutoProcessor.from_pretrained(f"unsloth/{model_name}"))
    tok = AutoTokenizer.from_pretrained(f"unsloth/{model_name}")
    if is_llama_model(model_name):
        tok = get_chat_template(tok, chat_template="llama-3.1")
        tok.chat_template = llama31_cot_template
    return tok


# What closes a finished model turn in Gemma 4's template. The template folds
# consecutive assistant messages into one turn, so a DSL continuation is
# trained -- and prompted by the testbench (its GEMMA continue_turn_suffix) --
# with the model turn left open on the block state, this cut off the end.
GEMMA4_TURN_END = "<turn|>\n"


def render_example(tok, model_name, convo, tool_list, instr_message):
    """Split one training conversation into (prompt_text, target_text).

    The single source of the train format: prompt_text is exactly what the
    model is prompted with at inference, target_text is everything loss is
    computed on -- the record's "output" and the turn end that follows it.

    Normally that is the prompt rendered with a generation header and the rest
    of the full rendering after it. Gemma 4 is the exception whenever the
    output continues an assistant state (almost every record): its template
    merges the two into one turn, trimmed and glued with no separator, so the
    full rendering does not start with the generation-header prompt and the
    split would land inside the output. There the prompt is the state's own
    turn left open, and the output goes after it on a blank line, the way the
    state's blocks are already separated.

    The chat template emits bos_token itself, so nothing adds one again.
    """
    messages = [{"role": "system", "content": instr_message}] + convo
    render = lambda msgs, gen: tok.apply_chat_template(
        msgs,
        tokenize=False,
        add_generation_prompt=gen,
        tools=tool_list,
        enable_thinking=False,
    )
    context, output = messages[:-1], messages[-1]["content"]

    if is_gemma4_model(model_name) and context[-1]["role"] == "assistant":
        closed = render(context, False)
        if not closed.endswith(GEMMA4_TURN_END):
            raise ValueError(
                f"{model_name}: the template did not close the state's turn with "
                f"{GEMMA4_TURN_END!r}, so it cannot be left open"
            )
        # Trimmed as the template trims every model message it renders.
        return closed[:-len(GEMMA4_TURN_END)], "\n\n" + output.strip() + GEMMA4_TURN_END

    prompt_text = render(context, True)
    full_text = render(messages, False)
    if not full_text.startswith(prompt_text):
        # The loss mask would start inside the output rather than at it --
        # what silently cost the first Gemma 4 run its block headers.
        raise ValueError(
            f"{model_name}: the chat template's full rendering does not start "
            f"with its generation prompt, so prompt and target cannot be split"
        )
    return prompt_text, full_text[len(prompt_text):]


def tokenize_example(tok, model_name, convo, tool_list, instr_message):
    """(prompt_ids, target_ids) for one conversation.

    Tokenized separately rather than as one string, as at inference: llama.cpp
    tokenizes the prompt on its own and the model produces the rest, so no
    token may straddle the boundary.
    """
    prompt_text, target_text = render_example(
        tok, model_name, convo, tool_list, instr_message
    )
    ids = lambda text: tok(text, add_special_tokens=False)["input_ids"]
    return ids(prompt_text), ids(target_text)


def make_formatting_func(tok, model_name, tool_list, instr_message, max_seq_len):
    """Factory that returns a formatting function bound to the given tokenizer.

    Everything up to and including the generation header is masked out: loss is
    computed only on the final assistant message (the record's "output"). The
    assistant blocks inside "input" are context -- they repeat across every step
    of a conversation and would be massively over-weighted if trained on.
    """
    def formatting_prompts_func(examples):
        convos = examples["messages"]
        all_input_ids = []
        all_attention_mask = []
        all_labels = []

        for convo in convos:
            prompt_ids, target_ids = tokenize_example(
                tok, model_name, convo, tool_list, instr_message
            )
            input_ids = prompt_ids + target_ids

            # Truncating would cut into the target; max_seq_len is measured from
            # this same split, so this only fires if the two ever disagree.
            if len(input_ids) > max_seq_len:
                continue

            labels = [-100] * len(prompt_ids) + target_ids

            all_input_ids.append(input_ids)
            all_attention_mask.append([1] * len(input_ids))
            all_labels.append(labels)

        return {
            "input_ids": all_input_ids,
            "attention_mask": all_attention_mask,
            "labels": all_labels
        }
    return formatting_prompts_func


def save_training_examples(tok_train, tokenizer, out_dir="inputs", n=3, run_name=None):
    """Write the first `n` tokenized samples exactly as the model sees them.

    Each sample is split at the loss boundary: the masked prefix
    (labels == -100, only conditioned on) and the target (labels != -100, the
    only tokens loss is computed on). Special tokens are kept visible so the
    dump matches the real token stream. Saved to inputs/inputs_<timestamp>.txt
    so every run leaves a human-readable record of what it actually trained on.
    """
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"inputs_{timestamp}.txt")

    n = min(n, len(tok_train))
    with open(path, "w", encoding="utf-8") as f:
        if run_name:
            f.write(f"run: {run_name}\n")
        f.write(f"saved: {timestamp}  |  first {n} of {len(tok_train)} training samples\n")
        for i in range(n):
            ex = tok_train[i]
            input_ids = ex["input_ids"]
            labels = ex["labels"]
            # The prefix is masked (-100) and contiguous, so its length is just
            # the count of leading -100s; the rest is the loss-bearing target.
            prompt_len = sum(1 for l in labels if l == -100)
            input_text = tokenizer.decode(input_ids[:prompt_len])
            output_text = tokenizer.decode(input_ids[prompt_len:])
            n_out = len(input_ids) - prompt_len
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"EXAMPLE {i + 1}/{n}  |  {len(input_ids)} tokens total, "
                    f"{n_out} in OUTPUT (loss computed on these)\n")
            f.write("=" * 80 + "\n")
            f.write("\n----- INPUT (fed to the model, loss masked) -----\n")
            f.write(input_text)
            f.write("\n\n----- OUTPUT (loss IS computed on these tokens) -----\n")
            f.write(output_text)
            f.write("\n")
    print(f"Saved {n} training example(s) to {path}")
    return path


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


class SaveThirdEpochCallback(TrainerCallback):
    """Saves LoRA adapters at the 1/3 and 2/3 marks of each epoch.

    A companion to SaveAdapterCallback's epoch-boundary saves: it drops two
    mid-epoch snapshots (at 0.33 and 0.66 of every epoch) so a run can be
    inspected or resumed from partway through an epoch. Step boundaries are
    computed from the optimizer-step count so the marks are exact under
    gradient accumulation.
    """
    # Fractional marks within each epoch: {fraction of epoch: name suffix}.
    MARKS = {0.33: "33", 0.66: "66"}

    def __init__(self, model, tokenizer, save_base, name_template):
        self.model = model
        self.tokenizer = tokenizer
        self.save_base = save_base
        self.name_template = name_template
        # {global_step at a fractional mark: fraction label, e.g. "0.33"}
        self.third_targets = {}

    def on_train_begin(self, args, state, control, **kwargs):
        # The f-th mark of epoch k lands at optimizer step
        # round(steps_per_epoch * (k + f)) for each fraction f.
        steps_per_epoch = state.max_steps / args.num_train_epochs
        self.third_targets = {
            round(steps_per_epoch * (k + frac)): f"{k}.{suffix}"
            for k in range(int(args.num_train_epochs))
            for frac, suffix in self.MARKS.items()
        }

    def on_step_end(self, args, state, control, **kwargs):
        label = self.third_targets.get(state.global_step)
        if label is None:
            return
        save_dir = f"{self.save_base}/{self.name_template.format(ep=label)}"
        self.model.save_pretrained(save_dir)
        self.tokenizer.save_pretrained(save_dir)
        print(f"Saved third-epoch adapter checkpoint to {save_dir}")


def make_short_name(model_name):
    """'Llama-3.2-3B-Instruct-unsloth-bnb-4bit' -> 'Llama-3.2-3B'"""
    name = model_name
    for suffix in ["-Instruct-unsloth-bnb-4bit", "-Instruct-bnb-8bit", "-Instruct", "-unsloth-bnb-4bit", "-bnb-8bit"]:
        name = name.replace(suffix, "")
    # Gemma's instruction-tuned marker ('gemma-4-E2B-it' -> 'gemma-4-E2B').
    # Stripped as a true suffix rather than added to the list above, where a bare
    # "-it" would corrupt any name containing those letters mid-string.
    if name.endswith("-it"):
        name = name[: -len("-it")]
    for prefix in ["Meta-"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def make_run_name(short_name, r, alpha, lr, lr_method, num_epochs, full_dataset=False):
    name = f"{short_name}-DSL_r{r}_a{alpha}_lr{lr:.0e}_{lr_method}_ep{num_epochs}"
    if full_dataset:
        name += "_full_dataset"
    return name


# ============================================================
# SECTION 6: TRAINING FUNCTION
# ============================================================
def run_training(model_name, r, alpha, lr, lr_method, num_epochs, save_adapter_per_epoch=False, full_dataset=False):
    """Single training run. Handles model loading, tokenization, training, saving, and cleanup."""
    short_name = make_short_name(model_name)
    run_name = make_run_name(short_name, r, alpha, lr, lr_method, num_epochs, full_dataset=full_dataset)
    save_dir = f"{SAVE_BASE}/adapters/{run_name}"

    print(f"\n{'='*60}")
    print(f"Starting run: {run_name}")
    print(f"{'='*60}")

    # Filtering is by rendered token count, so it needs the tokenizer -- which
    # is also how the context window gets sized to the data instead of a guess.
    raw_train_dataset, max_seq_length = build_train_dataset(make_tokenizer(model_name), model_name)
    print(f"max_seq_length set to {max_seq_length}")

    # Llama uses the project's 8-bit setup (LOAD_IN_* above); gpt-oss, Gemma 4 and
    # any other model ship pre-quantized and load in 4-bit.
    extra_model_kwargs = {}
    if is_llama_model(model_name):
        load_in_4bit, load_in_8bit = LOAD_IN_4BIT, LOAD_IN_8BIT
    else:
        load_in_4bit, load_in_8bit = True, False
        if is_gpt_oss_model(model_name):
            # gpt-oss's attention sinks default to torch flex_attention. Without a
            # FlashAttention2 build (unavailable on this Windows setup), the backward
            # falls back to torch's eager sdpa_dense_backward kernel, which has a bf16
            # bug: softmax scores get cast to the bf16 query dtype while grad_out
            # stays fp32, so the final matmul mixes Float and BFloat16 and raises
            # "expected scalar type Float but found BFloat16". Forcing eager attention
            # avoids that path -- gpt-oss's eager_attention_forward implements sinks
            # correctly, so this is numerically sound, just slower than flex/FA2.
            #
            # Scoped to gpt-oss on purpose: this used to apply to every non-Llama
            # model, which would needlessly drop Gemma 4 off unsloth's own attention
            # path. Gemma 4 has no sinks and no such bug.
            extra_model_kwargs["attn_implementation"] = "eager"

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=f"unsloth/{model_name}",
        max_seq_length=max_seq_length,
        dtype=DTYPE,
        load_in_4bit=load_in_4bit,
        load_in_8bit=load_in_8bit,
        full_finetuning=False,
        **extra_model_kwargs,
    )
    # Multimodal checkpoints (Gemma 4) hand back a processor here, not a tokenizer.
    tokenizer = as_tokenizer(tokenizer)
    model = FastLanguageModel.get_peft_model(
        model,
        r=r,
        lora_alpha=alpha * r,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=12345,
        use_rslora=False,
        loftq_config=None,
        **make_lora_kwargs(model_name),
    )
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Trainable LoRA parameters: {trainable_params:,}")
    # Which modules LoRA actually landed on. Worth printing every run: a silently
    # attention-only attach is how the gpt-oss MoE experts went untrained, and the
    # towers must stay absent for Gemma 4 (see make_lora_kwargs). MoE experts are
    # adapted as nn.Parameters rather than modules, so they show up in the count
    # above rather than in this list.
    lora_names = [name for name, _ in model.named_modules() if ".lora_A" in name]
    adapted = sorted({name.rsplit(".lora_A", 1)[0].split(".")[-1] for name in lora_names})
    print(f"LoRA attached to {len(lora_names)} modules: {adapted}")
    leaked = sorted({
        name.rsplit(".lora_A", 1)[0]
        for name in lora_names if "vision" in name or "audio" in name
    })
    if leaked:
        print(f"WARNING: LoRA leaked into non-language towers "
              f"({len(leaked)} modules), e.g. {leaked[:3]}")

    if is_llama_model(model_name):
        tokenizer = get_chat_template(tokenizer, chat_template="llama-3.1")
        tokenizer.chat_template = llama31_cot_template

    formatting_func = make_formatting_func(tokenizer, model_name, tools, instruction_message, max_seq_length)
    tok_train = raw_train_dataset.map(
        formatting_func,
        batched=True,
        keep_in_memory=True,
        remove_columns=raw_train_dataset.column_names,
    )
    dropped = len(raw_train_dataset) - len(tok_train)
    if dropped:
        print(f"Dropped {dropped} samples that exceeded max_seq_length={max_seq_length}")

    save_training_examples(tok_train, tokenizer, n=3, run_name=run_name)

    name_template = make_run_name(short_name, r, alpha, lr, lr_method, "{ep}", full_dataset=full_dataset)
    callbacks = []
    if save_adapter_per_epoch:
        callbacks.append(SaveAdapterCallback(model, tokenizer, f"{SAVE_BASE}/adapters", name_template))
    # Mid-epoch snapshots (0.33, 0.66, 1.33, ...) go to the checkpoints dir.
    callbacks.append(SaveThirdEpochCallback(model, tokenizer, f"{SAVE_BASE}/checkpoints", name_template))

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
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "dataset_fraction": DATASET_FRACTION,
            "train_samples": len(tok_train),
            "max_seq_length": max_seq_length,
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
        seed=12345,
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
        max_seq_length=max_seq_length,
        packing=False,
        callbacks=callbacks,
        args=training_args,
    )

    trainer.train()

    if not save_adapter_per_epoch:
        model.save_pretrained(save_dir)
        tokenizer.save_pretrained(save_dir)

    wandb.finish()

    del model, trainer, tok_train
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
    # No eval split exists any more -- every run trains on the whole dataset.
    # The flag only tags the run name, kept so run_grid.py keeps working.
    parser.add_argument("--full-dataset", action="store_true")
    args = parser.parse_args()

    run_training(
        model_name=args.model_name,
        r=args.r,
        alpha=args.alpha,
        lr=args.lr,
        lr_method=args.lr_method,
        num_epochs=args.num_epochs,
        save_adapter_per_epoch=args.save_adapter_per_epoch,
        full_dataset=args.full_dataset,
    )
