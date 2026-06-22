"""The executable program model (DSL §5).

A :class:`Program` is a list of :class:`Step` s. Each step is either *Linear*
(primitives only) or *Branching* (optional leading temp/remember lines + ordered
``when``/``otherwise`` arms).

Each :class:`Primitive` knows how to **render** its program-line text (using bound
phrases) and how to **resolve** against the running :class:`EvalContext` into a
:class:`Resolved` — the RESOLUTION lines it contributes and the ordered
:class:`ToolSpec` s it unwinds to (§5.5). Tool state-effects (§3.1) are attached
to each :class:`ToolSpec` so the interpreter can apply them as results arrive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from dataset_generation.blocks import render_tool_call
from dataset_generation.context import EvalContext
from dataset_generation.dsl_state import DslState
from dataset_generation.helpers import Expr, fmt


@dataclass
class ToolSpec:
    name: str
    render_args: list
    kwargs: dict
    apply: Callable[[DslState, dict], None]

    def call_str(self) -> str:
        return render_tool_call(self.name, self.render_args)


@dataclass
class Resolved:
    res_lines: List[str] = field(default_factory=list)
    tools: List[ToolSpec] = field(default_factory=list)


# ============================== primitives ===============================

class Primitive:
    is_answer: bool = False

    def render(self, ctx: EvalContext) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def resolve(self, ctx: EvalContext) -> Resolved:
        return Resolved()


class CheckGripper(Primitive):
    def render(self, ctx):
        return "check gripper"

    def resolve(self, ctx):
        return Resolved(tools=[ToolSpec(
            "get_gripper_state", [], {},
            lambda s, env: s.apply_get_gripper_state(env["content"]),
        )])


class CheckPosition(Primitive):
    def render(self, ctx):
        return "check position"

    def resolve(self, ctx):
        return Resolved(tools=[ToolSpec(
            "get_position_state", [], {},
            lambda s, env: s.apply_get_position_state(env["content"]),
        )])


class GoTo(Primitive):
    """``go to <Position>`` — position is a literal name or an Expr (e.g. memory)."""

    def __init__(self, position):
        self.position = position

    def _name_and_text(self, ctx):
        if isinstance(self.position, Expr):
            return self.position.eval(ctx)[0], self.position.text(ctx)
        return self.position, self.position

    def render(self, ctx):
        _, text = self._name_and_text(ctx)
        return f"go to {text}"

    def resolve(self, ctx):
        name, _ = self._name_and_text(ctx)
        lines = []
        if isinstance(self.position, Expr):
            lines = self.position.eval(ctx)[1]
        if name:
            ctx.state.apply_move_to(name)
        return Resolved(res_lines=lines, tools=[ToolSpec(
            "move_to", [name], {"position": name},
            lambda s, env, n=name: s.apply_move_to(n),
        )])


class OpenGripper(Primitive):
    def render(self, ctx):
        return "open gripper"

    def resolve(self, ctx):
        return Resolved(tools=[ToolSpec(
            "open_gripper", [], {}, lambda s, env: s.apply_open_gripper())])


class CloseGripper(Primitive):
    def render(self, ctx):
        return "close gripper"

    def resolve(self, ctx):
        return Resolved(tools=[ToolSpec(
            "close_gripper", [], {}, lambda s, env: s.apply_close_gripper())])


class LocateHere(Primitive):
    def render(self, ctx):
        return "locate here"

    def resolve(self, ctx):
        view = ctx.view

        def apply(s, env):
            s.apply_locate(s.position, view.observe_coverage.get(s.position, []), env["content"])

        return Resolved(tools=[ToolSpec("locate_shapes", [], {}, apply)])


def _observe_tools(ctx, poses: List[str]) -> List[ToolSpec]:
    view = ctx.view
    tools: List[ToolSpec] = []
    for p in poses:
        tools.append(ToolSpec("move_to", [p], {"position": p},
                              lambda s, env, n=p: s.apply_move_to(n)))
        tools.append(ToolSpec("locate_shapes", [], {},
                              lambda s, env, n=p: s.apply_locate(
                                  n, view.observe_coverage.get(n, []), env["content"])))
    return tools


class Observe(Primitive):
    """``observe [<A>, ...]`` — scan each covering pose not yet visited."""

    def __init__(self, roles):
        self.roles = list(roles)

    def render(self, ctx):
        inner = ", ".join(ctx.binding.phrase(r) for r in self.roles)
        if len(self.roles) > 1:
            return f"observe [{inner}]"
        return f"observe {inner}"

    def _poses(self, ctx) -> List[str]:
        wanted = set()
        for r in self.roles:
            wanted.update(ctx.binding.locations(r))
        poses: List[str] = []
        for pose in ctx.view.observe_poses:
            if pose in ctx.state.visited:
                continue
            if set(ctx.view.observe_coverage[pose]) & wanted:
                poses.append(pose)
        return poses

    def resolve(self, ctx):
        poses = self._poses(ctx)
        return Resolved(res_lines=[f"observe poses = {fmt(poses)}"],
                        tools=_observe_tools(ctx, poses))


class ApproachObserve(Primitive):
    """``approach observe <A>`` — move to a covering observe pose (no scan)."""

    def __init__(self, role):
        self.role = role

    def render(self, ctx):
        return f"approach observe {ctx.binding.phrase(self.role)}"

    def resolve(self, ctx):
        wanted = set(ctx.binding.locations(self.role))
        pose = next((p for p in ctx.view.observe_poses
                     if set(ctx.view.observe_coverage[p]) & wanted), None)
        tools = []
        if pose is not None:
            tools = [ToolSpec("move_to", [pose], {"position": pose},
                              lambda s, env, n=pose: s.apply_move_to(n))]
        return Resolved(res_lines=[f"observe poses = {fmt([pose] if pose else [])}"], tools=tools)


class ObserveEverything(Primitive):
    def render(self, ctx):
        return "observe everything"

    def resolve(self, ctx):
        poses = [p for p in ctx.view.observe_poses if p not in ctx.state.visited]
        return Resolved(res_lines=[f"observe poses = {fmt(poses)}"],
                        tools=_observe_tools(ctx, poses))


class PickFrom(Primitive):
    """``pick from <loc>`` -> move_to(pick pose); close_gripper()."""

    def __init__(self, loc_expr: Expr):
        self.loc_expr = loc_expr

    def render(self, ctx):
        return f"pick from {self.loc_expr.text(ctx)}"

    def resolve(self, ctx):
        loc = self.loc_expr.eval(ctx)[0]
        typ = ctx.state.scans.get(loc)
        pose = ctx.view.pick_pose(typ, loc) if loc else None
        lines = [
            f"L = {self.loc_expr.text(ctx)} = {fmt(loc)}",
            f"T = scans[{loc}] = {fmt(typ)}",
        ]
        tools = [
            ToolSpec("move_to", [pose], {"position": pose},
                     lambda s, env, n=pose: s.apply_move_to(n)),
            ToolSpec("close_gripper", [], {},
                     lambda s, env, t=typ, l=loc: (s.apply_close_gripper(t), s.after_pick(l))),
        ]
        # forward-predict deterministic effects so later primitives in the same
        # step resolve against the post-pick state (DSL §6 top-down resolution)
        if pose:
            ctx.state.apply_move_to(pose)
        ctx.state.apply_close_gripper(typ)
        if loc:
            ctx.state.after_pick(loc)
        return Resolved(res_lines=lines, tools=tools)


class PlaceAt(Primitive):
    """``place at <loc>`` -> move_to(place pose); open_gripper()."""

    def __init__(self, loc_expr: Expr):
        self.loc_expr = loc_expr

    def render(self, ctx):
        return f"place at {self.loc_expr.text(ctx)}"

    def resolve(self, ctx):
        loc = self.loc_expr.eval(ctx)[0]
        held = ctx.state.held
        pose = ctx.view.place_pose(held, loc) if loc else None
        lines = [
            f"L = {self.loc_expr.text(ctx)} = {fmt(loc)}",
            f"X = held = {fmt(held)}",
        ]
        tools = [
            ToolSpec("move_to", [pose], {"position": pose},
                     lambda s, env, n=pose: s.apply_move_to(n)),
            ToolSpec("open_gripper", [], {},
                     lambda s, env, l=loc, x=held: (s.apply_open_gripper(), s.after_place(l, x))),
        ]
        if pose:
            ctx.state.apply_move_to(pose)
        ctx.state.apply_open_gripper()
        if loc:
            ctx.state.after_place(loc, held)
        return Resolved(res_lines=lines, tools=tools)


class ApproachPick(Primitive):
    """``approach pick of <X> at <loc>`` -> move_to(pick pose)."""

    def __init__(self, type_expr: Expr, loc_expr: Expr):
        self.type_expr = type_expr
        self.loc_expr = loc_expr

    def render(self, ctx):
        return f"approach pick of {self.type_expr.text(ctx)} at {self.loc_expr.text(ctx)}"

    def resolve(self, ctx):
        loc = self.loc_expr.eval(ctx)[0]
        typ = self.type_expr.eval(ctx)[0]
        pose = ctx.view.pick_pose(typ, loc) if loc else None
        lines = [f"L = {self.loc_expr.text(ctx)} = {fmt(loc)}"]
        tools = [ToolSpec("move_to", [pose], {"position": pose},
                          lambda s, env, n=pose: s.apply_move_to(n))]
        return Resolved(res_lines=lines, tools=tools)


class Remember(Primitive):
    def __init__(self, name: str, expr: Expr):
        self.name = name
        self.expr = expr

    def render(self, ctx):
        return f"remember {self.name} = {self.expr.text(ctx)}"

    def resolve(self, ctx):
        value, lines = self.expr.eval(ctx)
        ctx.state.memory[self.name] = value
        return Resolved(res_lines=lines)


class Temp(Primitive):
    def __init__(self, name: str, expr: Expr):
        self.name = name
        self.expr = expr

    def render(self, ctx):
        return f"temp {self.name} = {self.expr.text(ctx)}"

    def resolve(self, ctx):
        value, _ = self.expr.eval(ctx)
        ctx.temps[self.name] = value
        return Resolved(res_lines=[f"{self.name} = {self.expr.text(ctx)} = {fmt(value)}"])


class Answer(Primitive):
    is_answer = True

    def __init__(self, key: str):
        self.key = key

    def render(self, ctx):
        return self.key

    def resolve(self, ctx):
        return Resolved()


# ================================ steps ==================================

@dataclass
class Arm:
    cond: Optional[Expr]   # None for the `otherwise` arm
    body: List[Primitive]

    def head_text(self, ctx: EvalContext, first: bool) -> str:
        if self.cond is None:
            return "otherwise:"
        return f"{'when' if first else 'otherwise when'} {self.cond.text(ctx)}:"


@dataclass
class Step:
    linear: Optional[List[Primitive]] = None
    pre: List[Primitive] = field(default_factory=list)
    arms: Optional[List[Arm]] = None

    @property
    def is_branching(self) -> bool:
        return self.arms is not None


def linear(*prims: Primitive) -> Step:
    return Step(linear=list(prims))


def branch(*arms: Arm, pre: Optional[List[Primitive]] = None) -> Step:
    return Step(pre=pre or [], arms=list(arms))


def when(cond: Expr, *body: Primitive) -> Arm:
    return Arm(cond=cond, body=list(body))


def otherwise(*body: Primitive) -> Arm:
    return Arm(cond=None, body=list(body))


@dataclass
class Program:
    steps: List[Step]

    def uses(self) -> "tuple[bool, bool]":
        """(uses_pick, uses_place) — drives scene compatibility (pose coverage)."""
        pick = place = False

        def scan(prims):
            nonlocal pick, place
            for p in prims:
                if isinstance(p, (PickFrom, ApproachPick)):
                    pick = True
                if isinstance(p, PlaceAt):
                    place = True

        for s in self.steps:
            if s.is_branching:
                scan(s.pre)
                for a in s.arms:
                    scan(a.body)
            else:
                scan(s.linear)
        return pick, place

    def render(self, ctx: EvalContext) -> str:
        out: List[str] = []
        for i, step in enumerate(self.steps, start=1):
            out.append(f"STEP {i}:")
            if step.is_branching:
                for p in step.pre:
                    out.append(f"  {p.render(ctx)}")
                for j, arm in enumerate(step.arms):
                    out.append(f"  {arm.head_text(ctx, first=(j == 0))}")
                    for p in arm.body:
                        out.append(f"    {p.render(ctx)}")
            else:
                for p in step.linear:
                    out.append(f"  {p.render(ctx)}")
        return "\n".join(out)
