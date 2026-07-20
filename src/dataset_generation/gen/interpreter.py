"""The DSL interpreter / conversation builder.

Executes a task program against a mutable ``SceneModel`` state and emits the
turn as a sequence of *invocations* (input/output text pairs), byte-faithful to
the block conventions in DSL.md / the walkthroughs.

Execution is split into **chunks**. A chunk is a maximal run of branch
evaluations followed by exactly one *boundary* statement (a ``remember`` write,
a primitive's tool call, or an ``answer``). One chunk maps to one or more
invocations:

* remember (non-tool) / answer  -> a single invocation
* a primitive with tool ops [o1, o2, ...] -> ``len(ops)+1`` invocations: the
  first emits the resolution + first tool call; each following invocation
  processes the previous tool result (a MEMORY delta) and emits the next call;
  the last also advances the cursor.

``cursor`` shown while a chunk is mid-flight is the chunk's *start* line; when a
chunk finishes it is set to the next chunk's start line (or ``done``).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from gen.program import Program, Node, IfChain, Branch, Answer, Remember, Prim
from gen.answers import AnswerResolver, Ctx
from gen.scene_model import SceneModel


TOOL_NAMES = {
    "list_positions": "list_avaliable_robot_positions",
    "get_position": "get_robot_position",
    "get_gripper": "get_gripper_state",
    "move": "move_robot_to",
    "open": "open_gripper",
    "close": "close_gripper",
    "locate": "locate_shapes",
}


class Invalid(Exception):
    """Raised when a program cannot validly execute against the current state
    (e.g. picking from an empty slot). The caller rejects this sample."""


# --- value rendering --------------------------------------------------------

def q(s: str) -> str:
    return f'"{s}"'


def jlist(xs) -> str:
    return "[" + ", ".join(q(str(x)) for x in xs) + "]"


def jdict(d) -> str:
    return "{" + ", ".join(f"{q(str(k))}: {q(str(v))}" for k, v in d.items()) + "}"


def jdict_bare(d) -> str:
    # scans / locate results are rendered without quotes (per the spec)
    return "{" + ", ".join(f"{k}: {v}" for k, v in d.items()) + "}"


def wrap(content: str) -> str:
    return f'{{status: "OK", content: {content}}}'


# --- steps ------------------------------------------------------------------

@dataclass
class ToolOp:
    call: str
    result: Optional[str] = None            # TOOL RESULTS line (plain form)
    mem_after: Dict[str, str] = field(default_factory=dict)
    append: Optional[Tuple[str, str]] = None  # (key, value) appended by CM (remember-tool form)


@dataclass
class Step:
    kind: str                               # 'remember'|'prim'|'answer'|'remember_tool'
    start_lineno: int
    res_lines: List[str] = field(default_factory=list)
    mem_delta: Dict[str, str] = field(default_factory=dict)
    tool_ops: List[ToolOp] = field(default_factory=list)
    answer_text: Optional[str] = None
    target: Optional[tuple] = None


class _Stop(Exception):
    pass


# --- model state carried across turns ---------------------------------------

@dataclass
class ModelState:
    scans: "OrderedDict[str,str]" = field(default_factory=OrderedDict)
    gripper: str = "unknown"                # open|closed|unknown
    held: str = "unknown"                   # <type>|none|unknown
    position: str = "unknown"               # <posname>|unknown
    explored: List[str] = field(default_factory=list)
    vars: Dict[str, object] = field(default_factory=dict)   # remember vars
    memory: "OrderedDict[str,str]" = field(default_factory=OrderedDict)  # rendered
    parsed: bool = False                    # parse-program done (turn 1)

    def copy(self) -> "ModelState":
        return ModelState(
            scans=OrderedDict(self.scans),
            gripper=self.gripper, held=self.held, position=self.position,
            explored=list(self.explored), vars=dict(self.vars),
            memory=OrderedDict(self.memory), parsed=self.parsed,
        )


# --- executor ---------------------------------------------------------------

class Executor:
    def __init__(self, scene: SceneModel, state: ModelState, resolver: AnswerResolver,
                 task_id: int, types: Dict[str, str], phrases: Dict[str, str],
                 locs: Dict[str, List[str]], p_position: Optional[str] = None):
        self.scene = scene
        self.st = state
        self.resolver = resolver
        self.task_id = task_id
        self.types = types
        self.phrases = phrases
        self.locs = locs
        self.p_position = p_position
        self.steps: List[Step] = []
        self._pending: List[str] = []
        self._pending_start: Optional[int] = None

    # --- top-level ---------------------------------------------------------

    def run(self, prog: Program) -> None:
        try:
            self._run_nodes(prog.body)
        except _Stop:
            pass

    def _run_nodes(self, nodes: List[Node]) -> None:
        for node in nodes:
            if isinstance(node, IfChain):
                self._run_if(node)
            elif isinstance(node, Remember):
                self._run_remember(node)
            elif isinstance(node, Prim):
                self._run_prim(node)
            elif isinstance(node, Answer):
                self._run_answer(node)

    # --- pending resolution bookkeeping -----------------------------------

    def _push_res(self, lineno: int, line: str):
        if self._pending_start is None:
            self._pending_start = lineno
        self._pending.append(line)

    def _take_pending(self, own_lineno: int, own_lines: List[str]) -> Tuple[int, List[str]]:
        start = self._pending_start if self._pending_start is not None else own_lineno
        lines = self._pending + own_lines
        self._pending = []
        self._pending_start = None
        return start, lines

    # --- control flow ------------------------------------------------------

    def _run_if(self, chain: IfChain) -> None:
        taken: Optional[Branch] = None
        for br in chain.branches:
            if br.kind in ("if", "elif"):
                val = self._eval_cond(br.cond)
                self._push_res(br.lineno, f"L{br.lineno} {self._subst(br.cond)} = {val}")
                if val:
                    taken = br
                    break
            else:  # else
                taken = br
                break
        if taken is not None and taken.body:
            sel = _first_lineno(taken.body)
            self._pending.append(f"   selected: L{sel}")
            self._run_nodes(taken.body)
        # no branch / empty body -> fall through to siblings (pending carries evals)

    # --- remember ----------------------------------------------------------

    def _run_remember(self, node: Remember) -> None:
        expr = node.expr.strip()
        if expr == "check position":
            start, lines = self._take_pending(
                node.lineno, [f"L{node.lineno} {node.name} = check position"])
            pos = self.scene.robot_position          # truth
            op = ToolOp(call=f"{node.name} = {TOOL_NAMES['get_position']}()",
                        append=(node.name, q(pos)))
            self.st.vars[node.name] = pos
            self.st.memory[node.name] = q(pos)
            self.steps.append(Step(kind="remember_tool", start_lineno=start,
                                   res_lines=lines, tool_ops=[op]))
            return
        value = self._eval_expr(expr)
        self.st.vars[node.name] = value
        rendered = self._render_var(value)
        start, lines = self._take_pending(
            node.lineno, [f"L{node.lineno} {node.name} = {rendered}"])
        delta = {node.name: rendered}
        self.st.memory[node.name] = rendered
        self.steps.append(Step(kind="remember", start_lineno=start,
                               res_lines=lines, mem_delta=delta))

    # --- primitives --------------------------------------------------------

    def _run_prim(self, node: Prim) -> None:
        kind = node.kind
        builder = getattr(self, f"_prim_{kind}", None)
        if builder is None:
            raise Invalid(f"unsupported primitive {kind!r}")
        res_lines, ops = builder(node)
        start, lines = self._take_pending(node.lineno, res_lines)
        self.steps.append(Step(kind="prim", start_lineno=start, res_lines=lines,
                               tool_ops=ops))

    def _prim_check_gripper(self, node):
        val = "open" if self.scene.gripper_open else "closed"   # truth
        result = wrap(q(val))
        self.st.gripper = val
        mem = {"gripper": val}
        if val == "open":
            mem["held"] = "none"
            self.st.held = "none"
        op = ToolOp(call=f"{TOOL_NAMES['get_gripper']}()",
                    result=f"{TOOL_NAMES['get_gripper']}() = {result}", mem_after=mem)
        return ([f"L{node.lineno} check gripper"], [op])

    def _prim_open_gripper(self, node):
        self.scene.gripper_open = True
        self.scene.held = None
        self.st.gripper = "open"
        self.st.held = "none"
        op = ToolOp(call=f"{TOOL_NAMES['open']}()",
                    result=f"{TOOL_NAMES['open']}() = {wrap(q(''))}",
                    mem_after={"gripper": "open", "held": "none"})
        return ([f"L{node.lineno} open gripper"], [op])

    def _prim_close_gripper(self, node):
        self.scene.gripper_open = False
        self.st.gripper = "closed"
        op = ToolOp(call=f"{TOOL_NAMES['close']}()",
                    result=f"{TOOL_NAMES['close']}() = {wrap(q(''))}",
                    mem_after={"gripper": "closed"})
        return ([f"L{node.lineno} close gripper"], [op])

    def _prim_observe(self, node):
        return self._observe(node, self._resolve_target(node.arg))

    def _prim_observe_everything(self, node):
        return self._observe(node, list(self.scene.canonical_order), everything=True)

    def _observe(self, node, target_locs, everything=False):
        cover = (self.scene.all_observe_cover(self.st.explored) if everything
                 else self.scene.cover_for(target_locs, self.st.explored))
        res = [f"L{node.lineno} observation positions = {jlist(cover)}"]
        ops: List[ToolOp] = []
        for pose in cover:
            ops.append(ToolOp(call=f"{TOOL_NAMES['move']}(position={q(pose)})",
                              result=f"{TOOL_NAMES['move']}(position={q(pose)}) = {wrap(q(''))}",
                              mem_after={"position": q(pose)}))
            self.st.position = pose
            self.st.explored.append(pose)
            occ = self.scene.locate_at(pose)
            # reveal ALL observable locations of this pose
            for loc in self.scene.revealed_locs([pose]):
                self.st.scans[loc] = occ.get(loc, "empty")
            self._reorder_scans()
            locate_content = jdict_bare(occ)
            ops.append(ToolOp(
                call=f"{TOOL_NAMES['locate']}()",
                result=f"{TOOL_NAMES['locate']}() = {wrap(locate_content)}",
                mem_after={"explored observation positions": jlist(self.st.explored),
                           "scans": self._scans_render()}))
        self.st.memory["explored observation positions"] = jlist(self.st.explored)
        self.st.memory["scans"] = self._scans_render()
        return (res, ops)

    def _prim_pick(self, node):
        loc = self.st.vars.get(node.arg)
        if not loc:
            raise Invalid("pick: loc is none")
        occ = self.st.scans.get(loc)
        if occ in (None, "empty"):
            raise Invalid("pick from empty slot")
        pick_pos = self.scene.pick_pos(occ, loc)
        if pick_pos is None:
            raise Invalid(f"no pick position for {occ}@{loc}")
        res = [f"L{node.lineno} pick location = {q(loc)}",
               f"   pick object = {occ}"]
        move = ToolOp(call=f"{TOOL_NAMES['move']}(position={q(pick_pos)})",
                      result=f"{TOOL_NAMES['move']}(position={q(pick_pos)}) = {wrap(q(''))}",
                      mem_after={"position": q(pick_pos)})
        self.st.position = pick_pos
        self.scene.robot_position = pick_pos
        self.st.scans[loc] = "empty"
        self.scene.occupancy[loc] = None
        self.st.held = occ
        self.st.gripper = "closed"
        self.scene.held = occ
        self.scene.gripper_open = False
        close = ToolOp(call=f"{TOOL_NAMES['close']}()",
                       result=f"{TOOL_NAMES['close']}() = {wrap(q(''))}",
                       mem_after={"gripper": "closed", "held": occ,
                                  "scans": self._scans_render()})
        self.st.memory["scans"] = self._scans_render()
        return (res, [move, close])

    def _prim_place(self, node):
        loc = self.st.vars.get(node.arg)
        if not loc:
            raise Invalid("place: loc is none")
        if self.st.held in ("none", "unknown"):
            raise Invalid("place: not holding a type")
        if self.st.scans.get(loc) != "empty":
            raise Invalid("place into non-empty slot")
        t = self.st.held
        place_pos = self.scene.place_pos(t, loc)
        if place_pos is None:
            raise Invalid(f"no place position for {t}@{loc}")
        res = [f"L{node.lineno} L = {q(loc)}", f"   X = held = {t}"]
        move = ToolOp(call=f"{TOOL_NAMES['move']}(position={q(place_pos)})",
                      result=f"{TOOL_NAMES['move']}(position={q(place_pos)}) = {wrap(q(''))}",
                      mem_after={"position": q(place_pos)})
        self.st.position = place_pos
        self.scene.robot_position = place_pos
        self.st.scans[loc] = t
        self.scene.occupancy[loc] = t
        self.st.held = "none"
        self.st.gripper = "open"
        self.scene.held = None
        self.scene.gripper_open = True
        opn = ToolOp(call=f"{TOOL_NAMES['open']}()",
                     result=f"{TOOL_NAMES['open']}() = {wrap(q(''))}",
                     mem_after={"gripper": "open", "held": "none",
                                "scans": self._scans_render()})
        self.st.memory["scans"] = self._scans_render()
        return (res, [move, opn])

    def _prim_get_from_user(self, node):
        t = self.types.get(node.arg, node.arg)
        self.st.held = t
        self.st.gripper = "closed"
        self.scene.held = t
        self.scene.gripper_open = False
        op = ToolOp(call=f"{TOOL_NAMES['close']}()",
                    result=f"{TOOL_NAMES['close']}() = {wrap(q(''))}",
                    mem_after={"gripper": "closed", "held": t})
        return ([f"L{node.lineno} getting {t}"], [op])

    def _prim_give_to_user(self, node):
        self.st.held = "none"
        self.st.gripper = "open"
        self.scene.held = None
        self.scene.gripper_open = True
        op = ToolOp(call=f"{TOOL_NAMES['open']}()",
                    result=f"{TOOL_NAMES['open']}() = {wrap(q(''))}",
                    mem_after={"gripper": "open", "held": "none"})
        return ([f"L{node.lineno} giving"], [op])

    def _goto(self, node, pos, label="position"):
        if pos is None:
            raise Invalid("goto: unknown position")
        self.st.position = pos
        self.scene.robot_position = pos
        op = ToolOp(call=f"{TOOL_NAMES['move']}(position={q(pos)})",
                    result=f"{TOOL_NAMES['move']}(position={q(pos)}) = {wrap(q(''))}",
                    mem_after={"position": q(pos)})
        return ([f"L{node.lineno} {label} = {q(pos)}"], [op])

    def _prim_goto_P(self, node):
        return self._goto(node, self.p_position)

    def _prim_goto_home(self, node):
        return self._goto(node, self.scene.home())

    def _prim_goto_observation(self, node):
        locs = self._resolve_target(node.arg)
        cover = self.scene.cover_for(locs, [])
        pose = cover[0] if cover else None
        return self._goto(node, pose, label="observation position")

    def _prim_goto_pick(self, node):
        # go to pick <typeexpr> from <loc>
        m = re.match(r"^(.*)\s+from\s+(.+)$", node.arg)
        typeexpr, locname = m.group(1).strip(), m.group(2).strip()
        loc = self.st.vars.get(locname, locname)
        t = self._eval_value_expr(typeexpr)
        pos = self.scene.pick_pos(t, loc)
        return self._goto(node, pos)

    def _prim_goto_memory(self, node):
        pos = self.st.vars.get("original position")
        return self._goto(node, pos)

    # --- answers -----------------------------------------------------------

    def _prebind_loc(self):
        """A few tasks reference ``loc`` in their answer without a preceding
        ``remember loc`` (authoring gap). Bind the intended value."""
        if "loc" in self.st.vars and self.st.vars["loc"]:
            return
        if self.task_id == 73:                       # first empty in A
            self.st.vars["loc"] = self._eval_first("A", "empty")
        elif self.task_id == 79:                     # a location holding X, anywhere
            self.st.vars["loc"] = self._eval_first("everything", "X")
        elif self.task_id == 100:                    # first empty anywhere
            self.st.vars["loc"] = self._eval_first("everything", "empty")

    def _run_answer(self, node: Answer) -> None:
        self._prebind_loc()
        if node.selection:
            chosen_macro = None
            branch_idx = None
            res_extra = []
            for idx, (cond, macro, _cnt) in enumerate(node.selection):
                if cond is None:
                    chosen_macro, branch_idx = macro, idx
                    break
                val = self._eval_cond(cond)
                res_extra.append(f"L{node.lineno} {self._subst(cond)} = {val}")
                if val:
                    chosen_macro, branch_idx = macro, idx
                    break
            if chosen_macro is None:
                # all conditions false and no else: no answer (should not happen)
                raise Invalid("answer selection produced no branch")
            macro = chosen_macro
            own = res_extra if res_extra else [f"L{node.lineno}"]
        else:
            macro = node.macro
            branch_idx = -1
            own = [f"L{node.lineno}"]

        text = self.resolver.resolve(macro, self._ctx())
        start, lines = self._take_pending(node.lineno, own)
        target = (self.task_id, node.label, branch_idx, macro)
        self.steps.append(Step(kind="answer", start_lineno=start, res_lines=lines,
                               mem_delta={"cursor": "done"}, answer_text=text,
                               target=target))
        raise _Stop()

    # --- evaluation --------------------------------------------------------

    def _ctx(self) -> Ctx:
        mem: Dict[str, str] = {}
        for k, v in self.st.vars.items():
            mem[k] = "" if v is None else str(v)
        mem["held"] = self.st.held
        mem["position"] = self.st.position
        mem["gripper"] = self.st.gripper
        scans = {k: v for k, v in self.st.scans.items()}
        types = dict(self.types)
        # in "place what you're holding" tasks X in the answer denotes the held type
        if "X" not in types and self.st.held not in ("none", "unknown"):
            types["X"] = self.st.held
        return Ctx(types=types, phrases=dict(self.phrases),
                   locs=dict(self.locs), mem=mem, scans=scans, home=self.scene.home() or "home")

    def _subst(self, text: str) -> str:
        from gen.program import substitute
        return substitute(text, {**self.phrases, **{k: v for k, v in self.types.items()}})

    def _canon(self, locs):
        idx = self.scene._order_index
        return sorted([l for l in locs], key=lambda l: idx.get(l, 10 ** 9))

    def _resolve_target(self, name: str) -> List[str]:
        name = name.strip()
        if name == "everything":
            return list(self.scene.canonical_order)
        # union over comma / 'and'
        parts = re.split(r"\s*,\s*|\s+and\s+", name)
        neg = False
        out: List[str] = []
        for p in parts:
            p = p.strip()
            if p.startswith("not "):
                neg = True
                p = p[4:].strip()
            if p in self.locs:
                out.extend(self.locs[p])
            elif p in self.st.vars and self.st.vars[p]:
                out.append(self.st.vars[p])
            elif p in self.scene.object_locations:
                out.append(p)
        if neg:
            base = set(out)
            out = [l for l in self.scene.canonical_order if l not in base]
        return self._canon(set(out))

    # value predicate over scans values
    def _make_pred(self, pred: str):
        pred = pred.strip()
        tX = self.types.get("X")
        tW = self.types.get("W")
        if pred in ("empty",):
            return lambda v: v == "empty"
        if pred in ("not empty", "not [empty]"):
            return lambda v: v != "empty"
        if pred == "X":
            return lambda v: v == tX
        if pred == "W":
            return lambda v: v == tW
        if pred in ("[X, W]", "[X,W]"):
            return lambda v: v in (tX, tW)
        if pred == "not W":
            return lambda v: v != tW
        if pred in ("not [X, empty]", "not [X,empty]"):
            return lambda v: v not in (tX, "empty")
        if pred == "not [X]":
            return lambda v: v != tX
        if pred == "MEMORY.held":
            return lambda v: v == self.st.held
        if pred == "reftype":
            rt = self.st.vars.get("reftype")
            return lambda v: v == rt
        # literal type
        return lambda v: v == pred

    def _eval_first(self, target: str, pred: Optional[str]) -> Optional[str]:
        locs = self._resolve_target(target)
        # only consider observed slots
        locs = [l for l in locs if l in self.st.scans]
        if pred is None:
            return locs[0] if locs else None
        fn = self._make_pred(pred)
        for loc in locs:
            if fn(self.st.scans[loc]):
                return loc
        return None

    def _eval_expr(self, expr: str):
        """Evaluate a remember RHS -> location name / type / None."""
        expr = expr.strip()
        m = re.match(r"^first in MEMORY\.scans\[(.+?)\]\s+where value is\s+(.+)$", expr)
        if m:
            return self._eval_first(m.group(1), m.group(2))
        m = re.match(r"^first in MEMORY\.scans\s+where value is\s+(.+)$", expr)
        if m:
            return self._eval_first("everything", m.group(1))
        m = re.match(r"^first in MEMORY\.scans\[(.+?)\]\s*$", expr)
        if m:
            return self._eval_first(m.group(1), None)
        m = re.match(r"^MEMORY\.scans\[(.+?)\]\s*$", expr)
        if m:
            return self._eval_value_expr(expr)
        raise Invalid(f"cannot evaluate expr {expr!r}")

    def _eval_value_expr(self, expr: str):
        """Evaluate an expression that yields a *type* (scans value)."""
        m = re.match(r"^MEMORY\.scans\[(.+?)\]\s*$", expr.strip())
        if m:
            var = m.group(1).strip()
            loc = self.st.vars.get(var, var)
            return self.st.scans.get(loc)
        if expr in self.types:
            return self.types[expr]
        return expr

    def _eval_cond(self, cond: str) -> bool:
        cond = cond.strip()
        # embedded "first ... is not none / is none"
        m = re.match(r"^(.*)\s+is not none$", cond)
        if m:
            return self._cond_value(m.group(1)) is not None
        m = re.match(r"^(.*)\s+is none$", cond)
        if m:
            return self._cond_value(m.group(1)) is None
        # gripper / held / position
        for key, attr in (("gripper", "gripper"), ("held", "held"), ("position", "position")):
            m = re.match(rf"^(?:MEMORY\.)?{key} is (.+)$", cond)
            if m:
                rhs = m.group(1).strip()
                cur = getattr(self.st, attr)
                if rhs == "unknown":
                    return cur == "unknown"
                if key == "gripper":
                    return cur == rhs
                if key == "held":
                    if rhs in ("X", "W"):
                        return cur == self.types.get(rhs)
                    return cur == rhs
                if key == "position":
                    if rhs == "home":
                        return cur == (self.scene.home() or "home")
                    return cur == rhs
        # A empty / B empty (and/or)
        if re.search(r"\bempty\b", cond) and " in " not in cond:
            return self._eval_emptiness(cond)
        # A full / A is not full
        m = re.match(r"^(\w)\s+is not full$", cond)
        if m:
            return not self._is_full(m.group(1))
        m = re.match(r"^(\w)\s+full$", cond)
        if m:
            return self._is_full(m.group(1))
        # X in A / X in A or X in B
        if " in " in cond:
            return self._eval_in(cond)
        raise Invalid(f"cannot evaluate condition {cond!r}")

    def _cond_value(self, expr: str):
        expr = expr.strip()
        if expr in self.st.vars:
            return self.st.vars[expr]
        # first ... expression
        try:
            return self._eval_expr(expr)
        except Invalid:
            return self.st.vars.get(expr)

    def _eval_emptiness(self, cond: str) -> bool:
        # supports: "A empty", "A empty and B empty", "A empty or B empty"
        if " and " in cond:
            return all(self._eval_emptiness(p) for p in cond.split(" and "))
        if " or " in cond:
            return any(self._eval_emptiness(p) for p in cond.split(" or "))
        m = re.match(r"^(\w)\s+empty$", cond.strip())
        if not m:
            raise Invalid(f"emptiness cond {cond!r}")
        return self._all_empty(m.group(1))

    def _target_locs_observed(self, tok: str) -> List[str]:
        return [l for l in self._resolve_target(tok) if l in self.st.scans]

    def _all_empty(self, tok: str) -> bool:
        locs = self._target_locs_observed(tok)
        return all(self.st.scans.get(l) == "empty" for l in locs) if locs else True

    def _is_full(self, tok: str) -> bool:
        locs = self._target_locs_observed(tok)
        return all(self.st.scans.get(l) not in (None, "empty") for l in locs) if locs else False

    def _eval_in(self, cond: str) -> bool:
        # e.g. "X in A", "X in A or X in B"
        if " or " in cond:
            return any(self._eval_in(p) for p in cond.split(" or "))
        if " and " in cond:
            return all(self._eval_in(p) for p in cond.split(" and "))
        m = re.match(r"^(\w+) in (\w)$", cond.strip())
        if not m:
            raise Invalid(f"in-cond {cond!r}")
        t = self.types.get(m.group(1), m.group(1))
        locs = self._target_locs_observed(m.group(2))
        return any(self.st.scans.get(l) == t for l in locs)

    # --- render helpers ----------------------------------------------------

    def _render_var(self, value) -> str:
        if value is None:
            return "none"
        if value in self.types.values():
            return str(value)          # a type
        return q(str(value))           # a location / position

    def _scans_render(self) -> str:
        return jdict_bare(self.st.scans)

    def _reorder_scans(self):
        idx = self.scene._order_index
        items = sorted(self.st.scans.items(), key=lambda kv: idx.get(kv[0], 10 ** 9))
        self.st.scans = OrderedDict(items)


def _first_lineno(nodes: List[Node]) -> int:
    n = nodes[0]
    if isinstance(n, IfChain):
        return n.branches[0].lineno
    return n.lineno
