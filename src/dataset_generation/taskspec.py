"""Task specification + the answer-prose environment.

A :class:`TaskSpec` is one entry from ``Tasks.md`` made executable: the prompt
template, the variable definitions (resolved per scene), the structured
:class:`Program`, and the per-outcome answer renderers.

Answers are callables ``(AnswerEnv) -> str`` so the exact wording from Tasks.md
(with its ``{loc}``/``{held}``/list placeholders) can be reproduced precisely
against the live post-execution state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from finetuning.models import VariableDefinition

from dataset_generation.context import EvalContext
from dataset_generation import helpers as H
from dataset_generation.program import Program


class AnswerEnv:
    """Read-only view used by answer callables to compose prose."""

    def __init__(self, ctx: EvalContext):
        self.ctx = ctx
        self.state = ctx.state
        self.binding = ctx.binding

    # role phrases / values
    @property
    def X(self) -> str:
        return self.binding.phrase("X") if "X" in self.binding else ""

    @property
    def W(self) -> str:
        return self.binding.phrase("W") if "W" in self.binding else ""

    @property
    def A(self) -> str:
        return self.binding.phrase("A") if "A" in self.binding else ""

    @property
    def B(self) -> str:
        return self.binding.phrase("B") if "B" in self.binding else ""

    @property
    def held(self) -> str:
        return self.state.held

    @property
    def position(self) -> str:
        return self.state.position

    @property
    def last_pick(self):
        return self.state.last_pick

    @property
    def last_place(self):
        return self.state.last_place

    # temp / memory
    def t(self, name: str):
        return self.ctx.temps.get(name)

    def m(self, name: str):
        return self.state.memory.get(name)

    # aggregate queries over the live state
    def count(self, role: str) -> int:
        return H._count(self.ctx, [role])

    def count_type(self, role: str, type_role: str) -> int:
        return H._count_of(self.ctx, [role], self.binding.type_value(type_role))

    def occupied(self, role: str) -> List[str]:
        return H._occupied_slots(self.ctx, [role])

    def empty(self, role: str) -> List[str]:
        return H._empty_slots(self.ctx, [role])

    def types(self, role: str) -> List[str]:
        return H.types_in(self.ctx, [role])

    def locations_holding(self, type_role: str) -> List[str]:
        t = self.binding.type_value(type_role)
        return [loc for loc, typ in self.state.scans.items() if typ == t]

    @property
    def scans(self) -> Dict[str, str]:
        return self.state.scans

    def occ_pairs(self, role: str):
        return [(loc, self.scans[loc]) for loc in self.occupied(role)]

    def desc(self, role: str) -> str:
        """``type in loc, type in loc`` over the occupied slots of a target."""
        return self.join(f"{typ} in {loc}" for loc, typ in self.occ_pairs(role))

    def locs_with(self, role: str, type_role: str) -> List[str]:
        t = self.binding.type_value(type_role)
        return [loc for loc in self.occupied(role) if self.scans[loc] == t]

    def n_locs(self, role: str) -> int:
        return len(self.binding.locations(role))

    def is_empty(self, role: str) -> bool:
        return self.count(role) == 0

    def is_full(self, role: str) -> bool:
        return self.count(role) == self.n_locs(role)

    def has(self, role: str, type_role: str) -> bool:
        t = self.binding.type_value(type_role)
        return any(self.scans.get(loc) == t for loc in self.binding.locations(role))

    def count_by_type(self, role: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for _, typ in self.occ_pairs(role):
            out[typ] = out.get(typ, 0) + 1
        return out

    def first_empty_scene(self):
        cov = H.covered_set(self.ctx)
        for loc in self.ctx.view.object_locations:
            if loc in cov and loc not in self.scans:
                return loc
        return None

    @staticmethod
    def join(items) -> str:
        return ", ".join(str(i) for i in items)


Answer = Callable[[AnswerEnv], str]


@dataclass
class TaskSpec:
    id: str
    header: str                       # prompt template, e.g. "Pick up $X from $A"
    intent: str                       # pick | place | query | move
    variables: List[VariableDefinition]
    program: Program
    answers: Dict[str, Answer]
    # which object type the robot starts out holding: a role name ("X"/"W"),
    # "any" (a random scene type), or None (gripper free / not applicable)
    held: Optional[str] = None
    # error fallback prose (used when a tool call fails mid-program)
    error_answer: Optional[Answer] = None
    notes: str = ""

    def role_names(self) -> List[str]:
        return [v.name.lstrip("$") for v in self.variables]
