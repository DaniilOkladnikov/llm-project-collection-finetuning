"""Helper and condition expressions (DSL §5.6 ObjectType helpers, §5.7 Location
helpers, §5.8 Conditions).

Every expression knows how to render its DSL text (using the bound *phrases*) and
how to evaluate against the running :class:`DslState` (using the bound
*locations/types*). Evaluation returns ``(value, resolution_lines)`` so the
RESOLUTION block is produced as a by-product of execution.

``value`` conventions:
* location / type finders -> a name string, or ``None`` ("none") when unmatched
* boolean conditions -> ``bool``
* counts -> ``int``
* list conditions -> ``list[str]`` (slot order)
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from dataset_generation.context import EvalContext

NONE = "none"


# --- value formatting -----------------------------------------------------

def fmt(value: Any) -> str:
    if value is None:
        return NONE
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


# --- low-level state queries ----------------------------------------------

def covered_set(ctx: EvalContext) -> set:
    s: set = set()
    for pose in ctx.state.visited:
        s.update(ctx.view.observe_coverage.get(pose, []))
    return s


def target_locations(ctx: EvalContext, roles: Sequence[str]) -> List[str]:
    """Concatenate the targets' locations (each already in slot order)."""
    locs: List[str] = []
    for r in roles:
        locs.extend(ctx.binding.locations(r))
    return locs


def target_text(ctx: EvalContext, roles: Sequence[str]) -> str:
    return ", ".join(ctx.binding.phrase(r) for r in roles)


def types_in(ctx: EvalContext, roles: Sequence[str]) -> List[str]:
    """Distinct types occupying the targets, in slot order."""
    seen: List[str] = []
    for loc in target_locations(ctx, roles):
        t = ctx.state.scans.get(loc)
        if t is not None and t not in seen:
            seen.append(t)
    return seen


# --- expression base ------------------------------------------------------

class Expr:
    def text(self, ctx: EvalContext) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def eval(self, ctx: EvalContext) -> Tuple[Any, List[str]]:  # pragma: no cover
        raise NotImplementedError

    def _leaf(self, ctx: EvalContext, value: Any) -> Tuple[Any, List[str]]:
        return value, [f"{self.text(ctx)} = {fmt(value)}"]


# --- literals / simple refs ----------------------------------------------

class TypeOf(Expr):
    """A bound object-type role (X/W) used as a literal type."""

    def __init__(self, role: str):
        self.role = role

    def text(self, ctx: EvalContext) -> str:
        return ctx.binding.phrase(self.role)

    def eval(self, ctx: EvalContext):
        # literal type: itself, no resolution line (DSL §5.6)
        return ctx.binding.type_value(self.role), []


class Held(Expr):
    def text(self, ctx: EvalContext) -> str:
        return "held"

    def eval(self, ctx: EvalContext):
        return ctx.state.held, []


class MemRef(Expr):
    def __init__(self, name: str):
        self.name = name

    def text(self, ctx: EvalContext) -> str:
        return self.name

    def eval(self, ctx: EvalContext):
        val = ctx.state.memory.get(self.name)
        # a memory holding a location list resolves to its first element (§5.7)
        if isinstance(val, list):
            return (val[0] if val else None), [f"{self.name} = {fmt(val[0] if val else None)}"]
        return val, []


def as_type_value(expr: Expr, ctx: EvalContext) -> Optional[str]:
    return expr.eval(ctx)[0]


class NumberLit(Expr):
    def __init__(self, n: int):
        self.n = n

    def text(self, ctx: EvalContext) -> str:
        return str(self.n)

    def eval(self, ctx: EvalContext):
        return self.n, []


class TempRef(Expr):
    """References a step-scoped temp variable (DSL §5.5.6)."""

    def __init__(self, name: str):
        self.name = name

    def text(self, ctx: EvalContext) -> str:
        return self.name

    def eval(self, ctx: EvalContext):
        return ctx.temps.get(self.name), []


class MemTrue(Expr):
    """A turn-memory value interpreted as a boolean (DSL §5.8 composition)."""

    def __init__(self, name: str):
        self.name = name

    def text(self, ctx: EvalContext) -> str:
        return self.name

    def eval(self, ctx: EvalContext):
        return self._leaf(ctx, bool(ctx.state.memory.get(self.name)))


class Position(Expr):
    """STATE.position (read from simulator ground truth at step start)."""

    def text(self, ctx: EvalContext) -> str:
        return "position"

    def eval(self, ctx: EvalContext):
        return ctx.sim_truth.get("position", ctx.state.position), []


def _named_value(ctx: EvalContext, name: str):
    """Look up a step temp first, then turn-scoped memory."""
    if name in ctx.temps:
        return ctx.temps[name]
    return ctx.state.memory.get(name)


class IsNotNone(Expr):
    def __init__(self, name: str):
        self.name = name

    def text(self, ctx: EvalContext) -> str:
        return f"{self.name} is not none"

    def eval(self, ctx: EvalContext):
        return self._leaf(ctx, _named_value(ctx, self.name) is not None)


class IsNone(Expr):
    def __init__(self, name: str):
        self.name = name

    def text(self, ctx: EvalContext) -> str:
        return f"{self.name} is none"

    def eval(self, ctx: EvalContext):
        return self._leaf(ctx, _named_value(ctx, self.name) is None)


# --- location finders (§5.7) ---------------------------------------------

class FirstEmptyIn(Expr):
    def __init__(self, roles: Sequence[str]):
        self.roles = list(roles)

    def text(self, ctx):
        return f"first empty in {target_text(ctx, self.roles)}"

    def eval(self, ctx):
        cov = covered_set(ctx)
        for loc in target_locations(ctx, self.roles):
            if loc in cov and loc not in ctx.state.scans:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


class FirstOccupiedIn(Expr):
    def __init__(self, roles: Sequence[str]):
        self.roles = list(roles)

    def text(self, ctx):
        return f"first occupied in {target_text(ctx, self.roles)}"

    def eval(self, ctx):
        for loc in target_locations(ctx, self.roles):
            if loc in ctx.state.scans:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


class FirstHoldingIn(Expr):
    def __init__(self, roles: Sequence[str], type_expr: Expr):
        self.roles = list(roles)
        self.type_expr = type_expr

    def text(self, ctx):
        return f"first in {target_text(ctx, self.roles)} holding {self.type_expr.text(ctx)}"

    def eval(self, ctx):
        t = as_type_value(self.type_expr, ctx)
        for loc in target_locations(ctx, self.roles):
            if ctx.state.scans.get(loc) == t:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


class FirstHoldingNotIn(Expr):
    def __init__(self, roles: Sequence[str], type_exprs: Sequence[Expr]):
        self.roles = list(roles)
        self.type_exprs = list(type_exprs)

    def text(self, ctx):
        types = ", ".join(e.text(ctx) for e in self.type_exprs)
        return f"first in {target_text(ctx, self.roles)} holding not {types}"

    def eval(self, ctx):
        excluded = {as_type_value(e, ctx) for e in self.type_exprs}
        for loc in target_locations(ctx, self.roles):
            t = ctx.state.scans.get(loc)
            if t is not None and t not in excluded:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


class FirstHolding(Expr):
    """Scene-wide, in scans insertion order."""

    def __init__(self, type_expr: Expr, outside: Optional[Sequence[str]] = None):
        self.type_expr = type_expr
        self.outside = list(outside) if outside else None

    def text(self, ctx):
        base = f"first holding {self.type_expr.text(ctx)}"
        if self.outside:
            base += f" outside {target_text(ctx, self.outside)}"
        return base

    def eval(self, ctx):
        t = as_type_value(self.type_expr, ctx)
        excluded = set(target_locations(ctx, self.outside)) if self.outside else set()
        for loc, typ in ctx.state.scans.items():
            if typ == t and loc not in excluded:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


class FirstEmpty(Expr):
    """Scene-wide first known-empty location (position-list order)."""

    def __init__(self, outside: Optional[Sequence[str]] = None):
        self.outside = list(outside) if outside else None

    def text(self, ctx):
        base = "first empty"
        if self.outside:
            base += f" outside {target_text(ctx, self.outside)}"
        return base

    def eval(self, ctx):
        cov = covered_set(ctx)
        excluded = set(target_locations(ctx, self.outside)) if self.outside else set()
        for loc in ctx.view.object_locations:
            if loc in cov and loc not in ctx.state.scans and loc not in excluded:
                return self._leaf(ctx, loc)
        return self._leaf(ctx, None)


# --- type finders (§5.6) --------------------------------------------------

class ATypeIn(Expr):
    def __init__(self, role: str, other_than: Optional[Expr] = None):
        self.role = role
        self.other_than = other_than

    def text(self, ctx):
        base = f"a type in {ctx.binding.phrase(self.role)}"
        if self.other_than is not None:
            base += f" other than {self.other_than.text(ctx)}"
        return base

    def eval(self, ctx):
        exclude = as_type_value(self.other_than, ctx) if self.other_than else None
        for loc in ctx.binding.locations(self.role):
            t = ctx.state.scans.get(loc)
            if t is not None and (exclude is None or t != exclude):
                return self._leaf(ctx, t)
        return self._leaf(ctx, None)


class ATypeSharedBy(Expr):
    def __init__(self, a: str, b: str):
        self.a, self.b = a, b

    def text(self, ctx):
        return f"a type shared by {ctx.binding.phrase(self.a)} and {ctx.binding.phrase(self.b)}"

    def eval(self, ctx):
        b_types = set(types_in(ctx, [self.b]))
        for t in types_in(ctx, [self.a]):
            if t in b_types:
                return self._leaf(ctx, t)
        return self._leaf(ctx, None)


class ATypeInNotIn(Expr):
    def __init__(self, a: str, b: str):
        self.a, self.b = a, b

    def text(self, ctx):
        return f"a type in {ctx.binding.phrase(self.a)} not in {ctx.binding.phrase(self.b)}"

    def eval(self, ctx):
        b_types = set(types_in(ctx, [self.b]))
        for t in types_in(ctx, [self.a]):
            if t not in b_types:
                return self._leaf(ctx, t)
        return self._leaf(ctx, None)


# --- conditions (§5.8) ----------------------------------------------------

class _BoolText(Expr):
    """Condition defined by a text template + a predicate over ctx."""

    def __init__(self, template: str, fn, roles: Sequence[str] = (), type_exprs: Sequence[Expr] = ()):
        self.template = template
        self.fn = fn
        self.roles = list(roles)
        self.type_exprs = list(type_exprs)

    def text(self, ctx):
        subs = {}
        if self.roles:
            for i, r in enumerate(self.roles):
                subs[f"A{i}"] = ctx.binding.phrase(r)
        for i, e in enumerate(self.type_exprs):
            subs[f"X{i}"] = e.text(ctx)
        return self.template.format(**subs)

    def eval(self, ctx):
        value = self.fn(ctx, self.roles, [as_type_value(e, ctx) for e in self.type_exprs])
        return self._leaf(ctx, value)


# -- robot conditions --

def gripper_is(state_value: str) -> Expr:
    return _BoolText(f"gripper is {state_value}",
                     lambda ctx, r, t: ctx.state.gripper == state_value)


def gripper_is_known() -> Expr:
    return _BoolText("gripper is known", lambda ctx, r, t: ctx.state.gripper != "unknown")


def holding_anything() -> Expr:
    return _BoolText("holding anything",
                     lambda ctx, r, t: ctx.state.held not in ("none", "unknown"))


def holding(type_expr: Expr) -> Expr:
    return _BoolText("holding {X0}", lambda ctx, r, t: ctx.state.held == t[0],
                     type_exprs=[type_expr])


def at_home() -> Expr:
    return _BoolText("at home", lambda ctx, r, t: ctx.state.position == "home")


# -- target conditions --

def _count(ctx, roles):
    return sum(1 for loc in target_locations(ctx, roles) if loc in ctx.state.scans)


def _count_of(ctx, roles, typ):
    return sum(1 for loc in target_locations(ctx, roles) if ctx.state.scans.get(loc) == typ)


def _empty_slots(ctx, roles):
    cov = covered_set(ctx)
    return [loc for loc in target_locations(ctx, roles)
            if loc in cov and loc not in ctx.state.scans]


def _occupied_slots(ctx, roles):
    return [loc for loc in target_locations(ctx, roles) if loc in ctx.state.scans]


def is_empty(role: str) -> Expr:
    return _BoolText("{A0} is empty", lambda ctx, r, t: _count(ctx, r) == 0, roles=[role])


def is_not_empty(role: str) -> Expr:
    return _BoolText("{A0} is not empty", lambda ctx, r, t: _count(ctx, r) > 0, roles=[role])


def is_full(role: str) -> Expr:
    return _BoolText(
        "{A0} is full",
        lambda ctx, r, t: all(loc in ctx.state.scans for loc in target_locations(ctx, r)),
        roles=[role],
    )


def has(role: str, type_expr: Expr) -> Expr:
    return _BoolText("{A0} has {X0}",
                     lambda ctx, r, t: any(ctx.state.scans.get(loc) == t[0]
                                           for loc in target_locations(ctx, r)),
                     roles=[role], type_exprs=[type_expr])


def has_no(role: str, type_expr: Expr) -> Expr:
    return _BoolText("{A0} has no {X0}",
                     lambda ctx, r, t: all(ctx.state.scans.get(loc) != t[0]
                                           for loc in target_locations(ctx, r)),
                     roles=[role], type_exprs=[type_expr])


def contains_only(role: str, type_expr: Expr) -> Expr:
    def fn(ctx, r, t):
        occ = _occupied_slots(ctx, r)
        return bool(occ) and all(ctx.state.scans[loc] == t[0] for loc in occ)
    return _BoolText("{A0} contains only {X0}", fn, roles=[role], type_exprs=[type_expr])


class Count(Expr):
    def __init__(self, role: str, type_expr: Optional[Expr] = None, empty: bool = False):
        self.role, self.type_expr, self.empty = role, type_expr, empty

    def text(self, ctx):
        if self.empty:
            return f"count of empty slots in {ctx.binding.phrase(self.role)}"
        if self.type_expr is not None:
            return f"count of {self.type_expr.text(ctx)} in {ctx.binding.phrase(self.role)}"
        return f"count in {ctx.binding.phrase(self.role)}"

    def eval(self, ctx):
        if self.empty:
            v = len(_empty_slots(ctx, [self.role]))
        elif self.type_expr is not None:
            v = _count_of(ctx, [self.role], as_type_value(self.type_expr, ctx))
        else:
            v = _count(ctx, [self.role])
        return self._leaf(ctx, v)


class ListExpr(Expr):
    """occupied / empty / types-in list conditions (value is a list)."""

    def __init__(self, kind: str, role: str):
        self.kind, self.role = kind, role  # kind: occupied|empty|types

    def text(self, ctx):
        p = ctx.binding.phrase(self.role)
        return {"occupied": f"occupied slots in {p}",
                "empty": f"empty slots in {p}",
                "types": f"types in {p}"}[self.kind]

    def eval(self, ctx):
        if self.kind == "occupied":
            v = _occupied_slots(ctx, [self.role])
        elif self.kind == "empty":
            v = _empty_slots(ctx, [self.role])
        else:
            v = types_in(ctx, [self.role])
        return self._leaf(ctx, v)


# -- cross-target conditions --

def more_empty_room(a: str, b: str) -> Expr:
    return _BoolText(
        "more empty room in {A0} than {A1}",
        lambda ctx, r, t: len(_empty_slots(ctx, [r[0]])) > len(_empty_slots(ctx, [r[1]])),
        roles=[a, b],
    )


def same_count(a: str, b: str) -> Expr:
    return _BoolText("same count in {A0} and {A1}",
                     lambda ctx, r, t: _count(ctx, [r[0]]) == _count(ctx, [r[1]]),
                     roles=[a, b])


# -- scene-wide conditions --

class LocationsHolding(Expr):
    def __init__(self, type_expr: Expr):
        self.type_expr = type_expr

    def text(self, ctx):
        return f"locations holding {self.type_expr.text(ctx)}"

    def eval(self, ctx):
        t = as_type_value(self.type_expr, ctx)
        v = [loc for loc, typ in ctx.state.scans.items() if typ == t]
        return self._leaf(ctx, v)


def no_location_holds(type_expr: Expr) -> Expr:
    return _BoolText("no location holds {X0}",
                     lambda ctx, r, t: not any(typ == t[0] for typ in ctx.state.scans.values()),
                     type_exprs=[type_expr])


def first_holding_exists(type_expr: Expr) -> Expr:
    return _BoolText("first holding {X0} exists",
                     lambda ctx, r, t: any(typ == t[0] for typ in ctx.state.scans.values()),
                     type_exprs=[type_expr])


def first_empty_location_exists() -> Expr:
    def fn(ctx, r, t):
        cov = covered_set(ctx)
        return any(loc in cov and loc not in ctx.state.scans for loc in ctx.view.object_locations)
    return _BoolText("first empty location exists", fn)


# --- composition (§5.8) ---------------------------------------------------

class BinOp(Expr):
    def __init__(self, op: str, left: Expr, right: Expr):
        self.op, self.left, self.right = op, left, right

    def text(self, ctx):
        return f"{self.left.text(ctx)} {self.op} {self.right.text(ctx)}"

    def eval(self, ctx):
        lv, llines = self.left.eval(ctx)
        rv, rlines = self.right.eval(ctx)
        value = _apply_op(self.op, lv, rv)
        return value, [*llines, *rlines, f"{self.text(ctx)} = {fmt(value)}"]


class Not(Expr):
    def __init__(self, inner: Expr):
        self.inner = inner

    def text(self, ctx):
        return f"not {self.inner.text(ctx)}"

    def eval(self, ctx):
        v, lines = self.inner.eval(ctx)
        value = not v
        return value, [*lines, f"{self.text(ctx)} = {fmt(value)}"]


def _apply_op(op: str, a: Any, b: Any) -> Any:
    if op == "and":
        return bool(a) and bool(b)
    if op == "or":
        return bool(a) or bool(b)
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == "==":
        return a == b
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    raise ValueError(f"unknown op {op}")
