"""Conversation builder: renders a turn's Steps into byte-faithful invocations,
maintaining the context-manager block state (PROGRAM / MEMORY / RESOLUTION /
TOOL CALL / TOOL RESULTS / ANSWER) and the persistent conversation memory.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional

from gen.interpreter import (Executor, ModelState, Step, ToolOp, jlist, jdict, q,
                             wrap, TOOL_NAMES)
from gen.program import Program, render_program_block
from gen.scene_model import SceneModel
from gen.answers import AnswerResolver


PARSE_PROGRAM_BLOCK = (
    "PROGRAM\n"
    "L1 remember avaliable positions = get positions\n"
    "L2 parse avaliable positions for objects\n"
    "L3 parse avaliable positions for locations\n"
    "L4 parse avaliable positions, locations for observation mapping\n"
    "L5 parse user"
)


class Conversation:
    def __init__(self, scene: SceneModel, resolver: AnswerResolver, conv_id: int):
        self.scene = scene
        self.resolver = resolver
        self.conv_id = conv_id
        self.history: List[tuple] = []              # (user_msg, answer_text)
        self.state = ModelState()                   # carried structured belief
        self.memory: "OrderedDict[str,str]" = OrderedDict()   # carried rendered memory
        self.invocations: List[dict] = []
        self.turns: List[dict] = []                 # per-turn metadata

        # ephemeral block state (reset per program/turn)
        self.user_msg = ""
        self.program_block: Optional[str] = None
        self.resolution: Optional[str] = None
        self.tool_calls: List[str] = []
        self.tool_results: Optional[str] = None
        self.last_answer: Optional[str] = None

    # --- block rendering ---------------------------------------------------

    def _mem_lines(self, mem) -> str:
        return "MEMORY\n" + "\n".join(f"{k} = {v}" for k, v in mem.items())

    def _render_input(self) -> str:
        parts: List[str] = []
        for (u, a) in self.history:
            parts.append(f"User: {u}\n\nANSWER\n{a}")
        parts.append(f"User: {self.user_msg}")
        if self.program_block:
            parts.append(self.program_block)
        if self.memory:
            parts.append(self._mem_lines(self.memory))
        if self.resolution:
            parts.append(self.resolution)
        if self.tool_calls:
            parts.append("TOOL CALL\n" + "\n".join(self.tool_calls))
        if self.tool_results:
            parts.append("TOOL RESULTS\n" + self.tool_results)
        return "\n\n".join(parts)

    def _render_output(self, b: dict) -> str:
        parts: List[str] = []
        if "program" in b:
            parts.append(b["program"])
        if "resolution" in b:
            parts.append(b["resolution"])
        if "memory" in b:
            parts.append(self._mem_lines(b["memory"]))
        if "toolcall" in b:
            parts.append("TOOL CALL\n" + b["toolcall"])
        if "answer" in b:
            parts.append("ANSWER\n" + b["answer"])
        return "\n\n".join(parts)

    def _emit(self, blocks: dict, tool_result: Optional[str] = None,
              append: Optional[tuple] = None) -> None:
        inp = self._render_input()
        out = self._render_output(blocks)
        self.invocations.append({"input": inp, "output": out})
        # apply output to accumulated state
        if "program" in blocks:
            self.program_block = blocks["program"]
            self.resolution = None
            self.tool_calls = []
            self.tool_results = None
        if "resolution" in blocks:
            self.resolution = blocks["resolution"]
            self.tool_calls = []
            self.tool_results = None
        if "memory" in blocks:
            for k, v in blocks["memory"].items():
                self.memory[k] = v
        if "toolcall" in blocks:
            self.tool_calls.append(blocks["toolcall"])
        if "answer" in blocks:
            self.last_answer = blocks["answer"]
        # context-manager post-processing (sets up next input)
        if append is not None:
            self.memory[append[0]] = append[1]
            self.tool_results = None
        elif tool_result is not None:
            self.tool_results = tool_result
        else:
            self.tool_results = None

    # --- parse prelude (turn 1) -------------------------------------------

    def _derive_objects_locations(self):
        objects: List[str] = []
        for name, cfg in self.scene.positions.items():
            if cfg["type"] in ("PICK", "PLACE") and cfg["bound_type"] not in objects:
                objects.append(cfg["bound_type"])
        locations = list(self.scene.canonical_order)
        return objects, locations

    def _render_observation_mapping(self) -> str:
        """observation mapping = dict of observe pose -> its observable locations,
        rendered per the spec e.g.
        {"observe_box1": "box1_1", "box1_2", "observe_box2": "box2_1", "box2_2"}."""
        parts: List[str] = []
        for name, locs in self.scene.observe_positions():
            ordered = self.scene.order(locs)
            parts.append(q(name) + ": " + ", ".join(q(l) for l in ordered))
        return "{" + ", ".join(parts) + "}"

    def _render_parse_prelude(self, parse_user_delta: dict, statechange_delta: dict):
        # P1: PROGRAM(parse) + initial belief memory
        init = OrderedDict()
        init["cursor"] = "L1"
        init["position"] = "unknown"
        init["gripper"] = "unknown"
        init["held"] = "unknown"
        self._emit({"program": PARSE_PROGRAM_BLOCK, "memory": init})

        # P2: RESOLUTION L1 + TOOL CALL (remember-tool form)
        avail = wrap(jlist(self.scene.position_names))
        self._emit({"resolution": "RESOLUTION\nL1",
                    "toolcall": f"avaliable positions = {TOOL_NAMES['list_positions']}()"},
                   append=("avaliable positions", avail))
        # P3: cursor advance
        self._emit({"memory": {"cursor": "L2"}})

        objects, locations = self._derive_objects_locations()
        # P4: parse objects
        self._emit({"resolution": "RESOLUTION\nL2",
                    "memory": {"objects": jlist(objects), "cursor": "L3"}})
        # P5: parse locations
        self._emit({"resolution": "RESOLUTION\nL3",
                    "memory": {"locations": jlist(locations), "cursor": "L4"}})
        # P6: parse observation mapping (advances cursor like every other parse step)
        self._emit({"resolution": "RESOLUTION\nL4",
                    "memory": {"observation mapping": self._render_observation_mapping(),
                               "cursor": "L5"}})
        # P7: parse user (+ state change)
        delta = OrderedDict()
        delta["cursor"] = "done"
        for k, v in parse_user_delta.items():
            delta[k] = v
        for k, v in statechange_delta.items():
            delta[k] = v
        self._emit({"resolution": "RESOLUTION\nL5", "memory": delta})
        self.state.parsed = True

    # --- step rendering ----------------------------------------------------

    def _res_block(self, lines: List[str]) -> str:
        return "RESOLUTION\n" + "\n".join(lines)

    def _render_step(self, step: Step, next_cursor: str):
        if step.kind in ("remember", "answer"):
            mem = OrderedDict(step.mem_delta)
            if step.kind == "remember":
                mem["cursor"] = next_cursor
            blocks = {"resolution": self._res_block(step.res_lines), "memory": mem}
            if step.kind == "answer":
                blocks["answer"] = step.answer_text
            self._emit(blocks)
            return

        if step.kind == "remember_tool":
            op = step.tool_ops[0]
            self._emit({"resolution": self._res_block(step.res_lines),
                        "toolcall": op.call}, append=op.append)
            self._emit({"memory": {"cursor": next_cursor}})
            return

        # prim
        ops = step.tool_ops
        if not ops:
            self._emit({"resolution": self._res_block(step.res_lines),
                        "memory": {"cursor": next_cursor}})
            return
        self._emit({"resolution": self._res_block(step.res_lines),
                    "toolcall": ops[0].call}, tool_result=ops[0].result)
        for k, op in enumerate(ops):
            is_last = (k == len(ops) - 1)
            mem = OrderedDict(op.mem_after)
            blocks = {"memory": mem}
            if is_last:
                mem["cursor"] = next_cursor
            else:
                blocks["toolcall"] = ops[k + 1].call
            self._emit(blocks, tool_result=(None if is_last else ops[k + 1].result))

    # --- public turn API ---------------------------------------------------

    def add_turn(self, task, prog: Program, user_msg: str,
                 types: Dict[str, str], phrases: Dict[str, str],
                 locs: Dict[str, List[str]], p_position: Optional[str],
                 parse_user_delta: dict, statechange_delta: dict,
                 first_turn: bool):
        """Render a turn whose Executor has already been run to produce
        ``prog``'s steps. Returns the reached target tuple."""
        self.user_msg = user_msg
        inv_start = len(self.invocations)
        # reset ephemeral program-scope blocks for a fresh program
        self.program_block = None
        self.resolution = None
        self.tool_calls = []
        self.tool_results = None

        # apply state_change to belief before executing
        for k, v in statechange_delta.items():
            if k == "gripper":
                self.state.gripper = v
            elif k == "held":
                self.state.held = v

        ex = Executor(self.scene, self.state, self.resolver, task.id,
                      types, phrases, locs, p_position,
                      rescan=getattr(task, "rescan", None))
        ex.run(prog)
        steps = ex.steps
        target = steps[-1].target if steps and steps[-1].kind == "answer" else None

        program_real = render_program_block(prog, {**phrases,
                                                   **{k: v for k, v in types.items()}})

        if first_turn and not self._prelude_done():
            self._render_parse_prelude(parse_user_delta, statechange_delta)
            real_init = OrderedDict({"cursor": "L1"})
        else:
            real_init = OrderedDict({"cursor": "L1"})
            for k, v in statechange_delta.items():
                real_init[k] = v
            for k, v in parse_user_delta.items():
                real_init[k] = v

        self._emit({"program": program_real, "memory": real_init})

        for i, step in enumerate(steps):
            nxt = steps[i + 1].start_lineno if i + 1 < len(steps) else None
            next_cursor = f"L{nxt}" if nxt is not None else "done"
            self._render_step(step, next_cursor)

        answer_text = steps[-1].answer_text if target else self.last_answer
        macro = target[3] if target else None
        macro_name = self.resolver.macro_name(macro) if macro else None
        self.history.append((user_msg, answer_text))
        self.turns.append({"task_id": task.id, "prompt": user_msg,
                           "answer": answer_text, "target": target})
        for inv in self.invocations[inv_start:]:
            inv["task_id"] = task.id
            inv["prompt"] = user_msg
            inv["answer"] = answer_text
            inv["answer_label"] = target[1] if target else None
            inv["answer_macro"] = macro_name
        return target, ex

    def _prelude_done(self) -> bool:
        return "avaliable positions" in self.memory
