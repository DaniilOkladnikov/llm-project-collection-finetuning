"""Fix existing datasets by expanding conversations for step-by-step training.

Each conversation with N tool calls + 1 final message is expanded into N+1
separate conversations, where each ends with an assistant message (either
a tool call or the final response).
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def expand_conversation(conv: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expand a single conversation into multiple step-by-step conversations.

    Each expanded conversation ends with an assistant message, allowing
    the model to learn to predict the next action given the history.
    """
    messages = conv.get("messages", [])
    original_metadata = conv.get("metadata", {})
    expanded = []

    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            # Create conversation ending at this assistant message
            sub_conv = {
                "messages": messages[:i + 1],
                "metadata": {
                    **original_metadata,
                    "step": len(expanded),
                    "is_final": not msg.get("tool_calls")
                }
            }
            expanded.append(sub_conv)

    return expanded


def fix_dataset(input_path: Path) -> None:
    """
    Read a dataset, expand all conversations, and overwrite the file.

    Args:
        input_path: Path to the dataset JSON file.
    """
    print(f"Reading dataset from: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    original_count = len(conversations)
    print(f"Found {original_count} conversations")

    # Expand all conversations
    expanded_conversations = []
    for conv in conversations:
        expanded = expand_conversation(conv)
        expanded_conversations.extend(expanded)

    expanded_count = len(expanded_conversations)
    print(f"Expanded to {expanded_count} conversations ({expanded_count / original_count:.1f}x)")

    # Overwrite the original file
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(expanded_conversations, f, indent=2)

    print(f"Saved expanded dataset to: {input_path}")


def get_latest_dataset() -> Path:
    """Get the most recently modified dataset file."""
    datasets_dir = Path(__file__).parent / "datasets"
    dataset_files = list(datasets_dir.glob("dataset_*.json"))

    if not dataset_files:
        raise FileNotFoundError(f"No dataset files found in {datasets_dir}")

    # Sort by modification time, most recent first
    dataset_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dataset_files[0]


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Use provided path
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"Error: File not found: {input_path}")
            sys.exit(1)
    else:
        # Use latest dataset
        try:
            input_path = get_latest_dataset()
            print(f"Using latest dataset: {input_path.name}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)

    fix_dataset(input_path)


if __name__ == "__main__":
    main()
