"""Generate fine-tuning dataset from scenario drafts across all scenes."""

import asyncio
import json
import random
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from finetuning.ScenarioRunner import (
    ScenarioRunner, get_available_scenes, load_scene_config, SCENES_DIR
)
from finetuning.models import Conversation, ConversationMessage


# Default configuration: draft_id -> conversations per scene (fractional OK)
DEFAULT_COUNTS: Dict[str, float] = {
    # ── 1.x observe_and_pick ──────────────────────────────
    "1.1": 4,      # success — core pick behavior
    "1.2": 0.5,    # gripper holding — early exit
    "1.4": 1,      # not found — teaches "searched but absent"
    # ── 2.x observe_and_place ─────────────────────────────
    "2.1": 4,      # success — core place behavior
    "2.2": 0.5,    # not holding — early exit
    "2.3": 0.5,    # wrong type — early exit
    "2.4": 0.5,    # all occupied — failure
    "2.5": 3,      # find empty in group — success variant
    # ── 3.x status_only (simple, 1-2 tool calls) ─────────
    "3.1": 2,      # what holding? (holding)
    "3.2": 2,      # what holding? (empty)
    "3.3": 1.5,    # holding X? (yes)
    "3.4": 1,      # holding X? (wrong type)
    "3.5": 1,      # holding X? (empty gripper)
    "3.6": 1.5,    # can pick? (yes)
    "3.7": 1,      # can pick? (no)
    "3.8": 1.5,    # what position?
    "3.8b": 1,     # what position? (holding)
    # ── 4.x navigate_to ──────────────────────────────────
    "4.1": 2,      # home
    "4.1b": 1,     # home (holding)
    "4.2": 2,      # observe Y
    "4.2b": 1,     # observe Y (holding)
    "4.4": 2,      # visit Y then Z
    "4.4b": 1,     # visit Y then Z (holding)
    "4.5": 2,      # go to pick position
    "4.5b": 1,     # go to pick position (holding)
    # ── 5.x observe_and_report ───────────────────────────
    "5.1": 2,      # what's at Y? (found)
    "5.1b": 1,     # what's at Y? (found, holding)
    "5.2": 1.5,    # what's at Y? (empty)
    "5.2b": 0.5,   # what's at Y? (empty, holding)
    "5.3": 2,      # is X at Y? (varies)
    "5.3b": 1,     # is X at Y? (holding)
    "5.4": 2,      # list objects in Y
    "5.4b": 1,     # list objects in Y (holding)
    "5.5": 2,      # count occupied
    "5.5b": 1,     # count occupied (holding)
    "5.6": 2,      # empty slots?
    "5.6b": 1,     # empty slots? (holding)
    "5.7": 2,      # where is X in Y?
    "5.7b": 1,     # where is X in Y? (holding)
    "5.8": 2,      # which has X: Y or Z?
    "5.8b": 1,     # which has X: Y or Z? (holding)
    "5.9": 2,      # count by type
    "5.9b": 1,     # count by type (holding)
    # ── 6.x observe_and_pick_any ─────────────────────────
    "6.1": 3,      # whatever at Y — success
    "6.2": 0.5,    # whatever at Y — empty
    "6.3": 3,      # Y else Z — found at Y (primary path)
    "6.4": 2,      # Y else Z — found at Z (fallback path)
    "6.5": 3,      # X or W — found X (primary)
    "6.6": 2,      # X or W — found W (secondary)
    "6.7": 0.5,    # X or W — empty
    "6.8": 0.0,    # X or W — neither
    "6.9": 3,      # unless W — success
    "6.10": 0.5,   # unless W — refused (only W present)
    "6.11": 0.5,   # unless W — empty
    # ── 7.x pick_return_origin ───────────────────────────
    "7.1": 3,      # get X, come back — success
    "7.2": 0.5,    # get X, come back — Y empty
    "7.3": 0.5,    # get X, come back — wrong type at Y
    "7.4": 2,      # conditional pick — X found
    "7.5": 1,      # conditional pick — not X (graceful return)
    "7.6": 2,      # pick whatever, bring back — success
    "7.7": 0.5,    # pick whatever, bring back — empty
    # ── 8.x search_all_and_place ─────────────────────────
    "8.1": 3,      # place somewhere — success
    "8.2": 0.5,    # place somewhere — all occupied
    "8.3": 2,      # prefer Y, Y full → placed elsewhere
    "8.4": 2,      # not at Y — success
    "8.5": 3,      # prefer Y, Y has room — success
    "8.6": 0.5,    # wrong type
    "8.7": 0.5,    # prefer Y, wrong type
    "8.8": 0.5,    # not at Y, wrong type
    # ── 9.x place_with_fallback ──────────────────────────
    "9.1": 3,      # Y else Z — Y empty, placed at Y
    "9.2": 2,      # Y else Z — Y full, placed at Z (fallback)
    "9.3": 0.5,    # Y else Z — both occupied
    "9.4": 2,      # strict only-if-empty — varies
    "9.5": 2,      # W-conditional — W found, redirect to Z
    "9.6": 2,      # W-conditional — no W, place at Y
    "9.7": 0.5,    # W-conditional — both full
    "9.8": 0.5,    # wrong type
    "9.9": 0.5,    # wrong type
    "9.10": 0.5,   # wrong type
    # ── 10.x pick_and_place (most complex routines) ──────
    "10.1": 4,     # move X from Y to Z — success
    "10.2": 0.5,   # move X — not at Y
    "10.3": 1,     # move X — Z occupied (no return)
    "10.4": 2,     # move X — Z full, returned to Y (fallback)
    "10.5": 0.5,   # move X return — not at Y
    "10.6": 0.5,   # move X return — Y empty
    "10.7": 3,     # pick any, place at Z — success
    "10.8": 0.5,   # pick any, place at Z — Y empty
    "10.9": 1,     # pick any, place at Z — Z occupied
    # ── 11.x search_all_and_pick ─────────────────────────
    "11.1": 4,     # find and pick — success
    "11.2": 0.5,   # find and pick — gripper busy
    "11.3": 1,     # find and pick — not found
    # ── 12.x observe_conditional_pick ──────────────────
    "12.1": 3,     # X found, picked — main success path
    "12.2": 2,     # different type found — report
    "12.3": 1.5,   # Y empty — report
    "12.4": 0.5,   # gripper busy — early exit
    # ── 13.x compare_inventories ───────────────────────
    "13.1": 2,     # varied counts
    "13.2": 1.5,   # tie
    # ── 14.x negated observation (observe_and_report_all)
    "14.1": 2,     # mixed empty/occupied
    "14.2": 1,     # all empty
    "14.3": 1,     # all full
    # ── 15.x place_implicit_type ───────────────────────
    "15.1": 3,     # success — core implicit place
    "15.2": 0.5,   # not holding — early exit
    "15.3": 0.5,   # Y full — failure
}

OUTPUT_DIR = Path(__file__).parent / "datasets"


def resolve_fractional_count(count: float) -> int:
    """Resolve a fractional count to an integer.

    int_part is guaranteed, fractional part is a probability of +1.
    Example: 2.5 → always 2, plus 50% chance of 3.
    """
    int_part = int(count)
    frac_part = count - int_part
    if frac_part > 0 and random.random() < frac_part:
        int_part += 1
    return int_part


def conversation_to_dict(conv: Conversation) -> Dict:
    """Convert Conversation model to dict format for dataset."""
    messages = []
    for msg in conv.messages:
        msg_dict = {"role": msg.role}
        if msg.content is not None:
            msg_dict["content"] = msg.content
        if msg.tool_calls:
            msg_dict["tool_calls"] = msg.tool_calls
        messages.append(msg_dict)

    return {
        "messages": messages,
        "metadata": conv.metadata
    }


async def generate_dataset(
    counts: Dict[str, float],
    output_path: Optional[Path] = None,
    system_prompt: Optional[str] = None
) -> List[Dict]:
    """
    Generate dataset of conversations.

    Args:
        counts: Dict mapping draft_id to conversations per scene (fractional OK).
        output_path: Path to save the dataset JSON. If None, uses default.
        system_prompt: Optional system prompt to prepend to each conversation.

    Returns:
        List of conversation dicts.
    """
    scenes = get_available_scenes()
    if not scenes:
        print(f"No scene files found in {SCENES_DIR}")
        return []

    print(f"Found {len(scenes)} scenes:")
    for s in scenes:
        print(f"  - {s.name}")

    drafts_path = Path(__file__).parent / "scenario_drafts.json"
    runner = ScenarioRunner(str(drafts_path))

    all_conversations: List[Dict] = []
    generated = 0
    failed = 0
    skipped = 0

    print(f"\nGenerating conversations across {len(counts)} drafts...")

    for scene_path in scenes:
        #if "scene_binA_001_gear" not in str(scene_path):
        #    continue
        scene_name = scene_path.stem
        scene_config = load_scene_config(scene_path)
        num_types = len(scene_config.object_types)
        print(f"\n=== Scene: {scene_name} ({num_types} types) ===")

        for draft_id in runner.scenario_drafts:
            if draft_id not in counts or counts[draft_id] <= 0:
                continue

            count = counts[draft_id]
            draft = runner.scenario_drafts[draft_id]

            # Scene-level type check
            if num_types < draft.min_object_types:
                skipped += 1
                continue

            actual_count = resolve_fractional_count(count)
            if actual_count == 0:
                continue

            print(
                f"  Draft {draft_id} ({draft.name}): "
                f"generating {actual_count} conversations"
            )

            for i in range(actual_count):
                try:
                    seed = hash(f"{scene_name}_{draft_id}_{i}") % (2**31)

                    conversation = await runner.run_scenario(
                        draft_id=draft_id,
                        scene_path=scene_path,
                        random_seed=seed
                    )

                    if conversation.metadata is None:
                        conversation.metadata = {}
                    conversation.metadata["generation_index"] = i

                    if system_prompt:
                        conversation.messages.insert(
                            0,
                            ConversationMessage(
                                role="system", content=system_prompt
                            )
                        )

                    conv_dict = conversation_to_dict(conversation)
                    all_conversations.append(conv_dict)
                    generated += 1

                except Exception as e:
                    print(f"    Error generating conversation {i}: {e}")
                    failed += 1

    print(f"\n=== Generation Complete ===")
    print(f"Generated: {generated} conversations")
    print(f"Failed: {failed}")
    print(f"Skipped (insufficient types): {skipped}")

    # Save dataset
    if output_path is None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"dataset_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_conversations, f, indent=2)

    print(f"Saved to: {output_path}")

    return all_conversations


async def main():
    """Main entry point."""
    await generate_dataset(
        DEFAULT_COUNTS)


if __name__ == "__main__":
    asyncio.run(main())
