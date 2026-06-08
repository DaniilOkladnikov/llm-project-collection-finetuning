"""Render every DSL block to its exact text form (DSL.md §1.6, §3-§9).

The interpreter assembles invocations from these strings. Formatting mirrors the
walkthroughs in DSL.md §10 (block header on its own line, content beneath).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .dsl_state import DslState


# --- value rendering ------------------------------------------------------

def render_value(value: Any) -> str:
    """Render a MAP/memory value: list -> ``[a, b]``, scalar -> ``str``."""
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def render_scans(scans: Dict[str, str]) -> str:
    if not scans:
        return "{}"
    return "{" + ", ".join(f"{loc}: {typ}" for loc, typ in scans.items()) + "}"


def render_visited(visited: Sequence[str]) -> str:
    return "[" + ", ".join(visited) + "]"


def render_memory(memory: Dict[str, Any]) -> str:
    if not memory:
        return "{}"
    return "{" + ", ".join(f"{k}: {render_value(v)}" for k, v in memory.items()) + "}"


# --- envelope / tool-result rendering -------------------------------------

def render_content(content: Any) -> str:
    """Render the ``content`` of a {status, content} envelope inside RESULTS."""
    if content is None:
        return ""
    if isinstance(content, dict):
        if not content:
            return "{}"
        return "{" + ", ".join(f"{k}: {v}" for k, v in content.items()) + "}"
    if isinstance(content, (list, tuple)):
        return ", ".join(str(v) for v in content)
    return str(content)


def render_tool_call(name: str, args: Optional[List[Any]] = None) -> str:
    inner = ", ".join(str(a) for a in (args or []))
    return f"{name}({inner})"


def _render_result_entry(call_str: str, envelope: Dict[str, Any]) -> str:
    status = envelope.get("status", "OK")
    content = render_content(envelope.get("content"))
    return (
        f"{call_str}: {{\n"
        f"  status: {status}\n"
        f"  content: {content}\n"
        f"}}"
    )


def render_results_block(header: str, entries: List[Tuple[str, Dict[str, Any]]]) -> str:
    lines = [header]
    for call_str, envelope in entries:
        lines.append(_render_result_entry(call_str, envelope))
    return "\n".join(lines)


# --- generated blocks -----------------------------------------------------

def render_precall(call_str: str) -> str:
    return f"PRECALL\n{call_str}"


def render_precall_results(entries: List[Tuple[str, Dict[str, Any]]]) -> str:
    return render_results_block("PRECALL RESULTS", entries)


def render_map(map_lines: List[Tuple[str, Any]]) -> str:
    lines = ["MAP"]
    for phrase, value in map_lines:
        lines.append(f"{phrase} = {render_value(value)}")
    return "\n".join(lines)


def render_state(state: DslState) -> str:
    return (
        "STATE\n"
        f"cursor: {state.cursor}\n"
        f"position: {state.position}\n"
        f"gripper: {state.gripper}\n"
        f"held: {state.held}\n"
        f"scans: {render_scans(state.scans)}\n"
        f"visited: {render_visited(state.visited)}\n"
        f"memory: {render_memory(state.memory)}"
    )


def render_program(program_text: str) -> str:
    return f"PROGRAM\n{program_text}"


def render_resolution(lines: List[str]) -> str:
    return "\n".join(["RESOLUTION", *lines])


def render_tools(calls: List[str]) -> str:
    return "\n".join(["TOOLS", *calls])


def render_tools_results(entries: List[Tuple[str, Dict[str, Any]]]) -> str:
    return render_results_block("TOOLS RESULTS", entries)


def render_outcome(answer_key: str) -> str:
    return f"OUTCOME\n{answer_key}"


def render_check() -> str:
    return "CHECK"


def render_error(message: Optional[str] = None) -> str:
    return "ERROR" if not message else f"ERROR\n{message}"


def render_answer(text: str) -> str:
    return f"ANSWER\n{text}"


def join_blocks(*blocks: Optional[str]) -> str:
    """Join non-empty blocks with a single blank line between them."""
    return "\n\n".join(b for b in blocks if b)
