"""Parse a task's pseudo-code program into an executable AST and render the
numbered ``PROGRAM`` block.

The grammar (surveyed from every task in tasks.yaml):

* simple primitives:   ``check gripper``, ``check position``, ``open gripper``,
  ``close gripper``, ``locate here``
* observe:             ``observe A``, ``observe A, B``, ``observe everything``
* pick / place:        ``pick from <var>``, ``place in <var>``
* user handoff:        ``get X from user``, ``give <held> to user``
* moving:              ``go to P``, ``go to home``, ``go to observation of A``,
  ``go to pick <typeexpr> from <loc>``, ``go to MEMORY.original position``
* memory:              ``remember <name> = <expr>``  (``let`` handled the same
  way but does not persist)
* control:             ``if <cond>:`` / ``elif <cond>:`` / ``else:``  (bodies by
  indentation)
* answers:             ``answer_N: <macro>``, ``answer_N:`` + indented
  ``if <cond>: <macro>`` selection branches, or a bare ``<macro>``.

Conditions and expressions are kept as raw strings; ``interpreter.py`` evaluates
them against the runtime state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# --- AST --------------------------------------------------------------------

@dataclass
class Node:
    lineno: int = 0
    indent: int = 0


@dataclass
class Prim(Node):
    kind: str = ""            # canonical primitive kind
    raw: str = ""             # original text (template, pre-substitution)
    arg: Optional[str] = None  # e.g. observe target / pick var / goto arg


@dataclass
class Remember(Node):
    name: str = ""
    expr: str = ""
    raw: str = ""
    is_let: bool = False


@dataclass
class Branch:
    kind: str                       # 'if' | 'elif' | 'else'
    cond: Optional[str]
    body: List[Node]
    lineno: int = 0
    indent: int = 0


@dataclass
class IfChain(Node):
    branches: List[Branch] = field(default_factory=list)


@dataclass
class Answer(Node):
    label: str = "answer_1"
    macro: Optional[str] = None                     # inline single macro
    count: int = 1                                  # required count for macro
    # selection branches: (cond|None, macro, count)
    selection: Optional[List[Tuple[Optional[str], str, int]]] = None
    raw: str = ""


@dataclass
class Program:
    body: List[Node]
    lines: List["PLine"] = field(default_factory=list)


@dataclass
class PLine:
    lineno: int
    indent: int
    text: str            # template text (pre-substitution)
    node: Node
    role: str            # 'stmt' | 'branch'
    branch: Optional[Branch] = None


# --- tokenising -------------------------------------------------------------

def _clean(text: str) -> str:
    # Keep the [N] answer counts (extracted later at macro sites); drop comments.
    text = re.sub(r"\s*#.*$", "", text)
    return text.rstrip()


def _split_count(macro_text: str) -> Tuple[str, int]:
    """Pull a trailing ``[N]`` count off a macro string."""
    m = re.search(r"\[(\d+)\]\s*$", macro_text)
    if m:
        return macro_text[: m.start()].strip(), int(m.group(1))
    return macro_text.strip(), 1


def _logical_lines(program_text: str) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for raw in program_text.split("\n"):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = _clean(raw.strip())
        if not text:
            continue
        out.append((indent, text))
    return out


_PRIM_KEYWORDS = (
    "check gripper", "check position", "open gripper", "close gripper",
    "locate here", "observe", "pick from", "place in", "get ", "give ",
    "go to",
)


def _is_control_if(text: str) -> bool:
    if not (text.startswith("if ") or text.startswith("elif ") or text == "else:"
            or text.startswith("else")):
        return False
    # control-flow if ends with ':' and has no inline value after it
    if text.startswith("else"):
        return text.rstrip().endswith(":")
    m = re.match(r"^(if|elif)\s+.*?:\s*(.*)$", text)
    return bool(m) and not m.group(2).strip()


# --- parser -----------------------------------------------------------------

class _Parser:
    def __init__(self, lines: List[Tuple[int, str]]):
        self.lines = lines
        self.i = 0

    def peek(self) -> Optional[Tuple[int, str]]:
        return self.lines[self.i] if self.i < len(self.lines) else None

    def parse_block(self, min_indent: int) -> List[Node]:
        nodes: List[Node] = []
        while self.i < len(self.lines):
            indent, text = self.lines[self.i]
            if indent < min_indent:
                break
            if _is_control_if(text):
                nodes.append(self.parse_ifchain(indent))
            elif re.match(r'^answer_\d+"?:', text):
                nodes.append(self.parse_answer(indent))
            elif self._is_bare_macro(text):
                self.i += 1
                macro, count = _split_count(text)
                nodes.append(Answer(indent=indent, label="answer_1",
                                    macro=_strip_quotes(macro), count=count))
            else:
                self.i += 1
                nodes.append(self.parse_simple(indent, text))
        return nodes

    def _is_bare_macro(self, text: str) -> bool:
        if any(text.startswith(k) for k in _PRIM_KEYWORDS):
            return False
        if text.startswith(("remember ", "let ", "if ", "elif", "else", "answer_",
                             "parse ")):
            return False
        # looks like a macro:  name  or  name(...)
        return bool(re.match(r"^[A-Za-z_][\w()\[\], .]*$", text))

    def parse_ifchain(self, indent: int) -> IfChain:
        branches: List[Branch] = []
        while self.i < len(self.lines):
            ci, ctext = self.lines[self.i]
            if ci != indent or not _is_control_if(ctext):
                break
            if ctext.startswith("if "):
                kind, cond = "if", ctext[3:].rstrip(":").strip()
            elif ctext.startswith("elif "):
                kind, cond = "elif", ctext[5:].rstrip(":").strip()
            else:
                kind, cond = "else", None
            self.i += 1
            body = self.parse_block(indent + 1)
            branches.append(Branch(kind=kind, cond=cond, body=body, indent=indent))
            nxt = self.peek()
            if not nxt or nxt[0] != indent:
                break
            if not (nxt[1].startswith("elif ") or nxt[1].startswith("else")):
                break
        return IfChain(indent=indent, branches=branches)

    def parse_answer(self, indent: int) -> Answer:
        _, text = self.lines[self.i]
        self.i += 1
        m = re.match(r'^(answer_\d+)"?:\s*(.*)$', text)
        label = m.group(1)
        rest = m.group(2).strip()
        if rest:
            macro, count = _split_count(rest)
            return Answer(indent=indent, label=label, macro=_strip_quotes(macro),
                          count=count)
        # sub-branch selection: following, more-indented, inline-if lines
        selection: List[Tuple[Optional[str], str, int]] = []
        while self.i < len(self.lines) and self.lines[self.i][0] > indent:
            _, btext = self.lines[self.i]
            self.i += 1
            mif = re.match(r"^(if|elif)\s+(.*?):\s*(.+)$", btext)
            mel = re.match(r"^else\s*:\s*(.+)$", btext)
            if mif:
                macro, count = _split_count(mif.group(3))
                selection.append((mif.group(2).strip(), _strip_quotes(macro), count))
            elif mel:
                macro, count = _split_count(mel.group(1))
                selection.append((None, _strip_quotes(macro), count))
        return Answer(indent=indent, label=label, selection=selection)

    def parse_simple(self, indent: int, text: str) -> Node:
        m = re.match(r"^(remember|let)\s+(.+?)\s*=\s*(.+)$", text)
        if m:
            return Remember(indent=indent, name=m.group(2).strip(),
                            expr=m.group(3).strip(), raw=text,
                            is_let=(m.group(1) == "let"))
        return Prim(indent=indent, kind=_prim_kind(text), raw=text,
                    arg=_prim_arg(text))


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s.strip()


def _prim_kind(text: str) -> str:
    if text == "check gripper":
        return "check_gripper"
    if text == "check position":
        return "check_position"
    if text == "open gripper":
        return "open_gripper"
    if text == "close gripper":
        return "close_gripper"
    if text == "locate here":
        return "locate_here"
    if text == "observe everything":
        return "observe_everything"
    if text.startswith("observe"):
        return "observe"
    if text.startswith("pick from"):
        return "pick"
    if text.startswith("place in"):
        return "place"
    if re.match(r"^get\s+.*\s+from user$", text):
        return "get_from_user"
    if re.match(r"^give\s+.*\s+to user$", text):
        return "give_to_user"
    if text.startswith("go to observation of"):
        return "goto_observation"
    if text.startswith("go to pick"):
        return "goto_pick"
    if text.startswith("go to home"):
        return "goto_home"
    if "original position" in text:
        return "goto_memory"
    if text.startswith("go to"):
        return "goto_P"
    return "unknown"


def _prim_arg(text: str) -> Optional[str]:
    if text.startswith("observe everything"):
        return "everything"
    if text.startswith("observe"):
        return text[len("observe"):].strip()
    if text.startswith("pick from"):
        return text[len("pick from"):].strip()
    if text.startswith("place in"):
        return text[len("place in"):].strip()
    if text.startswith("go to observation of"):
        return text[len("go to observation of"):].strip()
    if text.startswith("go to pick"):
        return text[len("go to pick"):].strip()
    if text.startswith("go to home"):
        return "home"
    if "original position" in text:
        return "MEMORY.original position"
    if text.startswith("go to"):
        return text[len("go to"):].strip()
    m = re.match(r"^get\s+(.+?)\s+from user$", text)
    if m:
        return m.group(1).strip()
    m = re.match(r"^give\s+(.+?)\s+to user$", text)
    if m:
        return m.group(1).strip()
    return None


# --- line numbering ---------------------------------------------------------

def _assign_lines(body: List[Node]) -> List[PLine]:
    lines: List[PLine] = []
    counter = [0]

    def emit(node: Node, indent: int, text: str, role: str, branch=None):
        counter[0] += 1
        node.lineno = counter[0] if role == "stmt" else node.lineno
        pl = PLine(lineno=counter[0], indent=indent, text=text, node=node,
                   role=role, branch=branch)
        lines.append(pl)
        return counter[0]

    def walk(nodes: List[Node], indent: int):
        for node in nodes:
            if isinstance(node, IfChain):
                for br in node.branches:
                    if br.kind == "if":
                        htext = f"if {br.cond}:"
                    elif br.kind == "elif":
                        htext = f"elif {br.cond}:"
                    else:
                        htext = "else:"
                    ln = emit(node, indent, htext, "branch", branch=br)
                    br.lineno = ln
                    walk(br.body, indent + 1)
            elif isinstance(node, Answer):
                emit(node, indent, node.label, "stmt")
            elif isinstance(node, Remember):
                emit(node, indent, node.raw, "stmt")
            elif isinstance(node, Prim):
                emit(node, indent, node.raw, "stmt")
    walk(body, 0)
    return lines


def parse_program(program_text: str) -> Program:
    lines = _logical_lines(program_text)
    parser = _Parser(lines)
    body = parser.parse_block(0)
    prog = Program(body=body)
    prog.lines = _assign_lines(body)
    return prog


# --- rendering the PROGRAM block --------------------------------------------

_TOKEN_RE = re.compile(r"(?<![\w])(A|B|C|X|W|P)(?![\w])")


def substitute(text: str, subst: dict) -> str:
    """Replace whole-token bindings (A,B,C,X,W,P) with their user phrases."""
    if not subst:
        return text
    def repl(m):
        tok = m.group(1)
        return subst.get(tok, tok)
    return _TOKEN_RE.sub(repl, text)


def render_program_block(prog: Program, subst: dict) -> str:
    out = []
    for pl in prog.lines:
        text = substitute(pl.text, subst)
        indent = "  " * pl.indent
        out.append(f"L{pl.lineno} {indent}{text}")
    return "PROGRAM\n" + "\n".join(out)


if __name__ == "__main__":
    from gen.taskfile import load_task_file
    tf = load_task_file()
    for tid in (1, 5, 20, 22, 37, 57, 112):
        t = tf.tasks[tid]
        prog = parse_program(t.program_text)
        print("==== task", tid)
        print(render_program_block(prog, {}))
        print()
