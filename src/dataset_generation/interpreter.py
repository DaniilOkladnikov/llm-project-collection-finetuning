"""The context-manager loop (DSL §1.5) that turns one resolved task into a
sequence of per-invocation ``{input, output, metadata}`` dataset entries.

Each invocation is one LLM forward pass. The interpreter plays both the
context-manager (assembling the I1/I2/I3 input per §1.3) and the model (emitting
the O1..O6 output per §1.4), running every tool call on the real simulator so the
TOOLS RESULTS are ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import blocks as B
from .context import Binding, EvalContext, SceneView
from .dsl_state import DslState
from .program import Program, Step
from .sim_driver import SimDriver
from .taskspec import AnswerEnv, TaskSpec


@dataclass
class Entry:
    input: str
    output: str
    metadata: Dict[str, Any]


class _Registry:
    """Latest rendered text of each block (the context manager's memory)."""

    def __init__(self, user_msg: str):
        self.user_msg = user_msg
        self.precall: Optional[str] = None
        self.precall_results: Optional[str] = None
        self.map: Optional[str] = None
        self.state: Optional[str] = None
        self.program: Optional[str] = None
        self.tools: Optional[str] = None
        self.tools_results: Optional[str] = None
        self.outcome: Optional[str] = None
        self.error: Optional[str] = None
        # bookkeeping
        self.tools_this_turn = False
        self.outcome_this_turn = False
        self.error_this_turn = False
        self.last_tool_ctx = "precall"   # "precall" | "tools"

    # --- input assembly (§1.3); conversations here are single-turn ---

    def I1(self) -> str:
        return B.join_blocks(self.user_msg, self.precall, self.precall_results)

    def I2(self) -> str:
        if self.last_tool_ctx == "tools":
            return B.join_blocks(self.tools, self.tools_results)
        return B.join_blocks(self.precall, self.precall_results)

    def I3(self) -> str:
        tail = self.error if self.error_this_turn else (
            self.outcome if self.outcome_this_turn else None)
        tools = self.tools if self.tools_this_turn else None
        tools_results = self.tools_results if self.tools_this_turn else None
        return B.join_blocks(
            self.user_msg, self.precall, self.precall_results,
            self.map, self.state, self.program,
            tools, tools_results, tail,
        )


class Interpreter:
    def __init__(self, task: TaskSpec, program: Program, binding: Binding,
                 view: SceneView, driver: SimDriver, initial_state: DslState,
                 metadata: Dict[str, Any]):
        self.task = task
        self.program = program
        self.driver = driver
        self.meta = metadata
        self.ctx = EvalContext(state=initial_state, binding=binding, view=view)
        self.reg = _Registry(self._user_message())
        self.entries: List[Entry] = []
        self._inv = 0

    # --- entry emission ---

    def _emit(self, input_text: str, output_text: str, combo: str) -> None:
        meta = dict(self.meta)
        meta.update({"invocation": self._inv, "combo": combo,
                     "cursor": self.ctx.state.cursor})
        self.entries.append(Entry(input=input_text, output=output_text, metadata=meta))
        self._inv += 1

    def _user_message(self) -> str:
        text = self.task.header
        for role in self.ctx.binding.roles.values():
            text = text.replace(f"${role.name}", role.phrase)
        return text

    def _refresh_sim_truth(self) -> None:
        status = self.driver.sim._cmd_get_robot_status()
        self.ctx.sim_truth = {
            "position": status["position"]["name"],
            "gripper": "open" if status["gripper_state"] == "open" else "closed",
        }

    # --- top-level run ---

    def run(self) -> List[Entry]:
        self._precall_phase()
        self._program_phase()
        return self.entries

    def _precall_phase(self) -> None:
        # Inv: I1 -> O1
        self._emit(self.reg.I1(), B.render_precall("get_positions()"), "O1")
        self.reg.precall = B.render_precall("get_positions()")
        env = self.driver.get_positions()
        self.reg.precall_results = B.render_precall_results([("get_positions()", env)])
        self.reg.last_tool_ctx = "precall"
        # Inv: I2 -> O3 (CHECK)
        self._emit(self.reg.I2(), B.render_check(), "O3")

    def _program_phase(self) -> None:
        state = self.ctx.state
        steps = self.program.steps
        i = 0
        while i < len(steps):
            step = steps[i]
            first = (i == 0)
            state.cursor = f"step_{i + 1}"
            self.ctx.temps = {}
            self._refresh_sim_truth()

            # Resolve against a forward scratch (predicts deterministic effects so
            # multi-primitive steps resolve top-down) while sharing the real
            # memory dict so `remember` writes persist across steps. The real
            # state is only advanced later, by actual tool execution.
            scratch = state.copy()
            scratch.memory = state.memory
            self.ctx.state = scratch
            res_lines, tools, answer_key = self._resolve_step(step)
            self.ctx.state = state

            # snapshot temps for answer prose (temps are step-scoped)
            answer_snapshot = dict(self.ctx.temps)

            state_block = B.render_state(state)
            tools_block = B.render_tools([t.call_str() for t in tools])
            outcome_block = B.render_outcome(answer_key) if answer_key else None

            if first:
                map_block = B.render_map(self._map_lines())
                program_block = B.render_program(self.program.render(self.ctx))
                output = B.join_blocks(map_block, state_block, program_block,
                                       B.render_resolution(res_lines), tools_block,
                                       outcome_block)
                self.reg.map = map_block
                self.reg.program = program_block
                input_text = self.reg.I1()
                combo = "O2"
            else:
                output = B.join_blocks(state_block, B.render_resolution(res_lines),
                                       tools_block, outcome_block)
                input_text = self.reg.I3()
                combo = "O5"

            self.reg.state = state_block
            self.reg.tools = tools_block
            if outcome_block:
                self.reg.outcome = outcome_block
                self.reg.outcome_this_turn = True
            self._emit(input_text, output, combo)

            errored = self._run_tools(tools)

            if errored:
                self._answer_invocation("error", answer_snapshot, error=True)
                return
            if answer_key:
                self._answer_invocation(answer_key, answer_snapshot)
                return
            i += 1

    def _resolve_step(self, step: Step):
        res_lines: List[str] = []
        tools = []
        answer_key: Optional[str] = None

        if not step.is_branching:
            res_lines.append("selected: linear")
            for p in step.linear:
                r = p.resolve(self.ctx)
                res_lines.extend(r.res_lines)
                tools.extend(r.tools)
                if p.is_answer:
                    answer_key = p.key
            return res_lines, tools, answer_key

        # branching: pre lines, then conditions in head order, then selected arm body
        for p in step.pre:
            r = p.resolve(self.ctx)
            res_lines.extend(r.res_lines)
            tools.extend(r.tools)

        selected = None
        selected_label = "fallthrough"
        for j, arm in enumerate(step.arms):
            if arm.cond is None:
                selected = arm
                selected_label = arm.head_text(self.ctx, first=(j == 0)).rstrip(":")
                break
            value, lines = arm.cond.eval(self.ctx)
            res_lines.extend(lines)
            if value:
                selected = arm
                selected_label = arm.head_text(self.ctx, first=(j == 0)).rstrip(":")
                break

        res_lines.append(f"selected: {selected_label}")

        if selected is not None:
            for p in selected.body:
                r = p.resolve(self.ctx)
                res_lines.extend(r.res_lines)
                tools.extend(r.tools)
                if p.is_answer:
                    answer_key = p.key
        return res_lines, tools, answer_key

    def _run_tools(self, tools) -> bool:
        """Run each tool, emitting a CHECK (or ERROR) invocation. Returns True on error."""
        results: List[Tuple[str, Dict[str, Any]]] = []
        for t in tools:
            env = self.driver.call(t.name, t.kwargs)
            results.append((t.call_str(), env))
            self.reg.tools_results = B.render_tools_results(results)
            self.reg.tools_this_turn = True
            self.reg.last_tool_ctx = "tools"
            if env["status"] == "OK":
                t.apply(self.ctx.state, env)
                self._emit(self.reg.I2(), B.render_check(), "O3")
            else:
                self.reg.error = B.render_error(env["content"])
                self.reg.error_this_turn = True
                self._emit(self.reg.I2(), B.render_error(env["content"]), "O4")
                return True
        return False

    def _answer_invocation(self, cursor: str, temps_snapshot: Dict[str, Any],
                           error: bool = False) -> None:
        self.ctx.state.cursor = cursor
        self.ctx.temps = temps_snapshot
        env = AnswerEnv(self.ctx)
        if error and self.task.error_answer is not None:
            text = self.task.error_answer(env)
        elif error:
            text = "I hit a problem and could not finish."
        else:
            text = self.task.answers[cursor](env)
        state_block = B.render_state(self.ctx.state)
        self.reg.state = state_block
        output = B.join_blocks(state_block, B.render_answer(text))
        self._emit(self.reg.I3(), output, "O6")

    # --- MAP generation (§4): identity for types & single locations, list for groups ---

    def _map_lines(self) -> List[Tuple[str, Any]]:
        lines: List[Tuple[str, Any]] = []
        for name in self.task.role_names():
            if name not in self.ctx.binding:
                continue
            # only phrases that actually appear in the prompt are mapped (DSL §4.1)
            if f"${name}" not in self.task.header:
                continue
            role = self.ctx.binding.get(name)
            if role.is_target:
                value = list(role.locations) if role.is_collection else role.phrase
            else:
                value = role.value
            lines.append((role.phrase, value))
        return lines
