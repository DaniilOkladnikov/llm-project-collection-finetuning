"""Verify every ``move_robot_to`` target in a dataset is a real robot position.

Walks ``datasets/dataset.json``, and for each invocation whose output contains a
``move_robot_to(position="...")`` tool call, checks the requested position
against the ``avaliable positions`` list the model could see in that
invocation's input memory.

Run with::

    python -m finetuning.observation_position_verifier [path/to/dataset.json]
                                                       [--json report.json]
                                                       [--limit N]
                                                       [--quiet]

Exit code is 1 when any invalid position is found, 0 otherwise.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "dataset.json"

MOVE_CALL = re.compile(r'move_robot_to\(\s*position\s*=\s*"((?:[^"\\]|\\.)*)"\s*\)')
# Any move call at all, so malformed ones (variables, missing quotes) are noticed
# rather than silently skipped.
ANY_MOVE_CALL = re.compile(r"move_robot_to\([^)]*\)")
POSITIONS_MEMORY = re.compile(r"avaliable positions = \{status:.*?content:\s*")
STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

Invocation = dict[str, Any]


@dataclass
class Finding:
    """One ``move_robot_to`` call that could not be validated."""

    key: str
    conversation_id: Any
    index_in_conversation: Any
    task_id: Any
    prompt: str
    kind: str  # "unknown-position" | "no-positions" | "unparsed-call"
    detail: str
    positions_source: str
    suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "conversation_id": self.conversation_id,
            "index_in_conversation": self.index_in_conversation,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "kind": self.kind,
            "detail": self.detail,
            "positions_source": self.positions_source,
            "suggestions": self.suggestions,
        }


def extract_bracketed(text: str, start: int) -> tuple[str, int] | None:
    """Return the ``[...]`` list starting at ``start`` plus the index after it.

    Bracket counting is string-aware because position names such as
    ``[slot_primary][chip_type_A]_PICKUP`` contain brackets themselves.
    """
    if start >= len(text) or text[start] != "[":
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    return None


def parse_available_positions(text: str) -> list[str] | None:
    """Pull the position names out of an ``avaliable positions = {...}`` memory line.

    The last occurrence wins: memory is appended to as a conversation proceeds,
    so the latest entry is what the model actually reads.
    """
    matches = list(POSITIONS_MEMORY.finditer(text))
    if not matches:
        return None

    for match in reversed(matches):
        extracted = extract_bracketed(text, match.end())
        if extracted is None:
            continue
        body, _ = extracted
        return [json.loads(literal.group(0)) for literal in STRING_LITERAL.finditer(body)]
    return None


def load_dataset(path: Path) -> dict[str, Invocation]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def conversation_positions(entries: dict[str, Invocation]) -> dict[Any, set[str]]:
    """Union of every position list seen anywhere in each conversation.

    Used as a fallback for invocations whose own input has no positions memory.
    """
    per_conversation: dict[Any, set[str]] = defaultdict(set)
    for entry in entries.values():
        positions = parse_available_positions(entry["input"])
        if positions:
            per_conversation[entry["metadata"]["conversation_id"]].update(positions)
    return per_conversation


def verify(entries: dict[str, Invocation]) -> tuple[list[Finding], dict[str, int]]:
    fallback = conversation_positions(entries)
    findings: list[Finding] = []
    stats = {"invocations": 0, "move_calls": 0, "checked": 0, "valid": 0}

    for key, entry in entries.items():
        stats["invocations"] += 1
        output = entry["output"]
        calls = ANY_MOVE_CALL.findall(output)
        if not calls:
            continue

        metadata = entry["metadata"]
        stats["move_calls"] += len(calls)

        positions = parse_available_positions(entry["input"])
        source = "input"
        if positions is None:
            conversation_fallback = fallback.get(metadata["conversation_id"])
            positions = sorted(conversation_fallback) if conversation_fallback else None
            source = "conversation" if positions else "missing"

        def make(kind: str, detail: str, suggestions: list[str] | None = None) -> Finding:
            return Finding(
                key=key,
                conversation_id=metadata.get("conversation_id"),
                index_in_conversation=metadata.get("index_in_conversation"),
                task_id=metadata.get("task_id"),
                prompt=metadata.get("prompt", ""),
                kind=kind,
                detail=detail,
                positions_source=source,
                suggestions=suggestions or [],
            )

        for call in calls:
            match = MOVE_CALL.fullmatch(call)
            if match is None:
                findings.append(make("unparsed-call", call))
                continue

            requested = match.group(1)
            if positions is None:
                findings.append(make("no-positions", requested))
                continue

            stats["checked"] += 1
            if requested in positions:
                stats["valid"] += 1
            else:
                findings.append(
                    make(
                        "unknown-position",
                        requested,
                        difflib.get_close_matches(requested, positions, n=3, cutoff=0.6),
                    )
                )

    return findings, stats


def report(findings: list[Finding], stats: dict[str, int], limit: int, quiet: bool) -> None:
    by_kind: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_kind[finding.kind].append(finding)

    if not quiet:
        for kind in ("unknown-position", "no-positions", "unparsed-call"):
            group = by_kind.get(kind)
            if not group:
                continue
            print(f"\n{kind}  ({len(group)})")
            print("-" * 72)
            for finding in group[:limit]:
                print(
                    f"  entry {finding.key}"
                    f"  conversation {finding.conversation_id}"
                    f"  invocation {finding.index_in_conversation}"
                    f"  task {finding.task_id}"
                )
                print(f"    prompt:   {finding.prompt}")
                print(f"    position: {finding.detail!r}  (positions from {finding.positions_source})")
                if finding.suggestions:
                    print(f"    close to: {', '.join(repr(s) for s in finding.suggestions)}")
            if len(group) > limit:
                print(f"  ... {len(group) - limit} more (raise --limit to see them)")

    print("\nsummary")
    print("-" * 72)
    print(f"  invocations scanned:   {stats['invocations']}")
    print(f"  move_robot_to calls:   {stats['move_calls']}")
    print(f"  positions checked:     {stats['checked']}")
    print(f"  positions valid:       {stats['valid']}")
    for kind in ("unknown-position", "no-positions", "unparsed-call"):
        print(f"  {kind + ':':<22} {len(by_kind.get(kind, []))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", nargs="?", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", type=Path, help="write the findings to this file")
    parser.add_argument("--limit", type=int, default=20, help="findings printed per kind")
    parser.add_argument("--quiet", action="store_true", help="print the summary only")
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(f"Dataset not found: {args.dataset}")

    findings, stats = verify(load_dataset(args.dataset))
    report(findings, stats, args.limit, args.quiet)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {"stats": stats, "findings": [f.as_dict() for f in findings]},
                handle,
                indent=2,
            )
        print(f"\nwrote {args.json}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
