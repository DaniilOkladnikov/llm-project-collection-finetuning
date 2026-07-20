"""Resolve an answer-macro string (as written in a task program) to the exact
text the model must emit.

The ``answers:`` block of tasks.yaml maps a macro *signature* to a template,
e.g. ``picked(X, loc) -> "I picked up {X} from {loc}"``. The template's
placeholders are the signature's formal parameters. A program answer such as
``picked(MEMORY.scans[loc], loc). atpos(MEMORY.original position)`` is a
``. ``-composition of one or more macro calls; each call's actual arguments are
resolved against a runtime ``Ctx`` and substituted into the template.

A handful of macros carry a *directive* rather than a prose template
(``nameobjects``, ``locof``, ``emptylocs``, ``projectedafter``); those are
computed in code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from gen.taskfile import _split_top_commas


@dataclass
class Ctx:
    types: Dict[str, str] = field(default_factory=dict)     # 'X'/'W' -> type
    phrases: Dict[str, str] = field(default_factory=dict)   # 'A'/'B'/'C'/'P' -> phrase
    locs: Dict[str, List[str]] = field(default_factory=dict)  # 'A' -> [loc,...]
    mem: Dict[str, str] = field(default_factory=dict)        # memory vars -> value
    scans: Dict[str, str] = field(default_factory=dict)      # loc -> type|'empty'
    home: str = "home"


def _parse_sig(sig: str) -> Tuple[str, List[str]]:
    m = re.match(r"^([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$", sig.strip())
    if not m:
        return sig.strip(), []
    name = m.group(1)
    params = []
    if m.group(2) and m.group(2).strip():
        params = [p.strip() for p in _split_top_commas(m.group(2))]
    return name, params


class AnswerResolver:
    def __init__(self, answers: Dict[str, str]):
        self.templates: Dict[str, str] = {}
        self.params: Dict[str, List[str]] = {}
        for sig, template in answers.items():
            name, params = _parse_sig(sig)
            self.templates[name] = template
            self.params[name] = params

    # --- public ------------------------------------------------------------

    def resolve(self, macro_text: str, ctx: Ctx) -> str:
        parts = _split_composition(macro_text)
        return ". ".join(self._resolve_one(p, ctx) for p in parts)

    def macro_name(self, macro_text: str) -> str:
        first = _split_composition(macro_text)[0]
        name, _args = _parse_call(first)
        return name

    # --- one macro call ----------------------------------------------------

    def _resolve_one(self, call: str, ctx: Ctx) -> str:
        name, args = _parse_call(call)

        if name in ("nameobjects", "locof", "emptylocs", "projectedafter"):
            return self._resolve_special(name, args, ctx)

        template = self.templates.get(name, name)
        formals = self.params.get(name, [])

        if name == "thereisno" and len(args) == 1:
            # "...without location means everywhere"
            val = _resolve_list(args[0], ctx)
            return f"There is no {val}"

        if name == "nospace2place" and not args:
            # empty argument means "in the whole scene"
            return "There is no empty space anywhere"

        out = template
        for i, formal in enumerate(formals):
            if i < len(args):
                value = self._resolve_value(formal, args[i], ctx)
            else:
                value = ""
            out = out.replace("{" + formal + "}", value)
        return out

    def _resolve_value(self, formal: str, arg: str, ctx: Ctx) -> str:
        if formal.startswith("L[") or arg.strip().startswith("["):
            return _resolve_list(arg, ctx)
        return _resolve_arg(arg, ctx)

    # --- directive macros --------------------------------------------------

    def _resolve_special(self, name: str, args: List[str], ctx: Ctx) -> str:
        if name == "nameobjects":
            locs = _target_locs(args[0], ctx)
            items = [f"{ctx.scans[l]} in {l}" for l in locs
                     if ctx.scans.get(l) not in (None, "empty")]
            return ", ".join(items) if items else "nothing"
        if name == "emptylocs":
            locs = _target_locs(args[0], ctx)
            empt = [l for l in locs if ctx.scans.get(l) == "empty"]
            return ", ".join(empt) if empt else "none"
        if name == "locof":
            # locof(X, [A]) / locof(X, everything): list locations holding X
            obj = _resolve_arg(args[0], ctx)
            locs = _target_locs(args[1], ctx) if len(args) > 1 else list(ctx.scans)
            hits = [l for l in locs if ctx.scans.get(l) == obj]
            where = ", ".join(hits) if hits else "nowhere"
            return f"There is {obj} in {where}"
        if name == "projectedafter":
            locs = _target_locs(args[0], ctx)
            phrase = _resolve_arg(args[0], ctx)
            removed = ctx.mem.get("loc")
            items = [f"{ctx.scans[l]} in {l}" for l in locs
                     if ctx.scans.get(l) not in (None, "empty") and l != removed]
            body = ", ".join(items) if items else "nothing"
            return f"Afterwards {phrase} would contain {body}"
        return name


# --- helpers ----------------------------------------------------------------

def _split_composition(text: str) -> List[str]:
    """Split ``a(...). b(...)`` on the top-level '. ' separators."""
    out, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "." and depth == 0 and i + 1 < len(text) and text[i + 1] == " ":
            out.append(cur.strip())
            cur = ""
            i += 2
            continue
        cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def _parse_call(call: str) -> Tuple[str, List[str]]:
    call = call.strip()
    m = re.match(r"^([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$", call)
    if not m:
        return call, []
    name = m.group(1)
    args = []
    if m.group(2) is not None and m.group(2).strip():
        args = [a.strip() for a in _split_top_commas(m.group(2))]
    return name, args


def _resolve_list(arg: str, ctx: Ctx) -> str:
    arg = arg.strip()
    if arg.startswith("[") and arg.endswith("]"):
        arg = arg[1:-1]
    elems = [e.strip() for e in _split_top_commas(arg) if e.strip()]
    return ", ".join(_resolve_arg(e, ctx) for e in elems)


def _target_locs(arg: str, ctx: Ctx) -> List[str]:
    """Locations referenced by a target argument (A / [A, B] / everything)."""
    arg = arg.strip()
    if arg.startswith("[") and arg.endswith("]"):
        arg = arg[1:-1]
    if arg in ("everything",):
        return list(ctx.scans)
    out: List[str] = []
    for e in _split_top_commas(arg):
        e = e.strip()
        out.extend(ctx.locs.get(e, []))
    # keep only observed locations, preserve given order
    return [l for l in out if l in ctx.scans]


def _resolve_arg(arg: str, ctx: Ctx) -> str:
    arg = arg.strip()
    if arg in ("X", "W"):
        return ctx.types.get(arg, arg)
    if arg in ("A", "B", "C"):
        return ctx.phrases.get(arg, arg)
    if arg == "P":
        return ctx.mem.get("position", ctx.phrases.get("P", arg))
    if arg.startswith("observation"):
        return ctx.mem.get("position", arg)
    if arg == "home":
        return ctx.home
    if arg == "MEMORY.held":
        return ctx.mem.get("held", "unknown")
    if arg == "MEMORY.position":
        return ctx.mem.get("position", "unknown")
    if arg == "MEMORY.original position":
        return ctx.mem.get("original position", "unknown")
    m = re.match(r"^MEMORY\.scans\[(.+)\]$", arg)
    if m:
        inner = m.group(1).strip()
        loc = ctx.mem.get(inner, inner)
        return ctx.scans.get(loc, "empty")
    if arg.startswith("MEMORY."):
        return ctx.mem.get(arg[len("MEMORY."):], arg)
    if arg in ctx.mem:
        return ctx.mem[arg]
    return arg
