"""Loader for tasks.yaml.

tasks.yaml is *not* valid YAML: the ``program`` blocks are indentation-sensitive
pseudo-code (double-quoted, but with meaningful leading whitespace that a YAML
parser would fold away). So we parse the file line-by-line ourselves:

* the ``answers:`` block  -> {macro_name: template_string}
* the ``tasks:`` block    -> {id: Task}

Each Task keeps the raw, de-indented program text (relative indentation
preserved) which ``program.py`` turns into an executable AST.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_PATH = os.path.join(_HERE, "tasks.yaml")


# --- macro signatures -------------------------------------------------------

@dataclass
class MacroSig:
    """A parsed answer-macro reference like ``picked(X, loc)``."""
    name: str
    args: List[str]

    @property
    def key(self) -> str:
        return self.name


def parse_macro_sig(text: str) -> MacroSig:
    text = text.strip()
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?\s*$", text)
    if not m:
        return MacroSig(name=text, args=[])
    name = m.group(1)
    argstr = m.group(2)
    args: List[str] = []
    if argstr is not None and argstr.strip():
        args = [a.strip() for a in _split_top_commas(argstr)]
    return MacroSig(name=name, args=args)


def _split_top_commas(s: str) -> List[str]:
    """Split on commas that are not nested inside brackets/parens."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
            cur += ch
        elif ch in ")]":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


# --- task container ---------------------------------------------------------

@dataclass
class Task:
    id: int
    prompts: List[str]
    program_text: str                       # de-indented raw pseudo-code
    state_change: Dict[str, str] = field(default_factory=dict)
    comes_only_after: List[MacroSig] = field(default_factory=list)
    rescan: Optional[str] = None            # 'add' | 'drop': prompt states the
                                            # scene changed -> force a re-observe
    ast: object = None                      # filled in by program.parse_program

    @property
    def is_canthelp(self) -> bool:
        return "canthelp" in self.program_text


@dataclass
class TaskFile:
    answers: Dict[str, str]                 # macro signature -> template
    tasks: Dict[int, Task]
    answer_ids: Dict[str, int] = field(default_factory=dict)   # macro NAME -> id


# --- answers parsing --------------------------------------------------------

# Legacy form:  "macro": "template"
_ANSWER_RE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*(#.*)?$')
# Current form: "macro": {id: N, text: "template"}
_ANSWER_ID_RE = re.compile(
    r'^\s*"((?:[^"\\]|\\.)*)"\s*:\s*\{\s*id\s*:\s*(\d+)\s*,\s*'
    r'text\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}\s*(#.*)?$')


def _parse_answers(lines: List[str]) -> Tuple[Dict[str, str], Dict[str, int]]:
    """Return (signature -> template, macro-name -> id).

    Ids are declared in tasks.yaml so they stay stable across regenerations; a
    macro written in the legacy id-less form simply has no id.
    """
    out: Dict[str, str] = {}
    ids: Dict[str, int] = {}
    for line in lines:
        m = _ANSWER_ID_RE.match(line)
        if m:
            sig, aid, template = m.group(1), int(m.group(2)), m.group(3)
            out[sig] = template
            ids[parse_macro_sig(sig).name] = aid
            continue
        m = _ANSWER_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out, ids


# --- program extraction -----------------------------------------------------

def _dedent_program(raw_lines: List[str]) -> str:
    """Strip the surrounding YAML quotes and normalise indentation.

    ``raw_lines`` are the lines that follow a ``program:`` key. Their common
    left margin is removed; relative indentation (which encodes control flow) is
    preserved. The opening/closing double quotes are stripped.
    """
    # Drop leading/trailing fully-blank lines.
    while raw_lines and not raw_lines[0].strip():
        raw_lines = raw_lines[1:]
    while raw_lines and not raw_lines[-1].strip():
        raw_lines = raw_lines[:-1]
    if not raw_lines:
        return ""

    base = len(raw_lines[0]) - len(raw_lines[0].lstrip(" "))

    out: List[str] = []
    for line in raw_lines:
        # Programs never contain a literal '#', so a '#' always starts a comment.
        line = re.sub(r"\s*#.*$", "", line)
        stripped = line[base:] if len(line) >= base else line.lstrip(" ")
        out.append(stripped.rstrip())

    # Drop trailing blank lines introduced by comment removal.
    while out and not out[-1].strip():
        out.pop()

    if out:
        # Strip the opening double-quote from the first non-blank line.
        first = out[0].lstrip()
        if first.startswith('"'):
            lead = len(out[0]) - len(out[0].lstrip())
            out[0] = out[0][:lead] + first[1:]
        # Strip the closing double-quote from the last non-blank line; if that
        # leaves the line empty, drop it entirely (e.g. a lone `" # comment`).
        last = out[-1].rstrip()
        if last.endswith('"'):
            out[-1] = last[:-1].rstrip()
            if not out[-1].strip():
                out.pop()

    return "\n".join(out).rstrip("\n")


def _parse_comes_only_after(value: str) -> List[MacroSig]:
    value = value.strip()
    # Drop a leading comment.
    value = re.sub(r"\s*#.*$", "", value).strip()
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1].strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    parts = _split_top_commas(value)
    return [parse_macro_sig(p) for p in parts if p.strip()]


def _parse_prompts(value: str) -> List[str]:
    value = value.strip()
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    # Fallback: a bare single string.
    return [value.strip().strip('"')]


def load_task_file(path: str = TASKS_PATH) -> TaskFile:
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    # Split into answers-section and tasks-section.
    tasks_idx = next(i for i, l in enumerate(lines) if l.rstrip() == "tasks:")
    answer_lines = lines[:tasks_idx]
    body = lines[tasks_idx + 1:]

    answers, answer_ids = _parse_answers(answer_lines)

    header_re = re.compile(r"^\s{1,4}(\d+):\s*$")
    blocks: List[Tuple[int, List[str]]] = []
    cur_id: Optional[int] = None
    cur_lines: List[str] = []
    for l in body:
        m = header_re.match(l)
        if m and (len(l) - len(l.lstrip(" "))) <= 4:
            if cur_id is not None:
                blocks.append((cur_id, cur_lines))
            cur_id = int(m.group(1))
            cur_lines = []
        elif cur_id is not None:
            cur_lines.append(l)
    if cur_id is not None:
        blocks.append((cur_id, cur_lines))

    tasks: Dict[int, Task] = {}
    for tid, blk in blocks:
        prompts: List[str] = []
        state_change: Dict[str, str] = {}
        coa: List[MacroSig] = []
        rescan: Optional[str] = None
        program_text = ""

        i = 0
        while i < len(blk):
            line = blk[i]
            s = line.strip()
            if s.startswith("rescan:"):
                rescan = re.sub(r"\s*#.*$", "", s[len("rescan:"):]).strip() or None
                i += 1
            elif s.startswith("prompts:"):
                prompts = _parse_prompts(s[len("prompts:"):])
                i += 1
            elif s.startswith("state_change:"):
                i += 1
                while i < len(blk):
                    s2 = blk[i].strip()
                    m = re.match(r"^-\s*([A-Za-z_ ]+):\s*(\S+)\s*$", s2)
                    if m:
                        state_change[m.group(1).strip()] = m.group(2).strip()
                        i += 1
                    else:
                        break
            elif s.startswith("comes only after:") or s.startswith("comes_only_after:"):
                val = s.split(":", 1)[1]
                coa = _parse_comes_only_after(val)
                i += 1
            elif s.startswith("program:"):
                # Everything after this line (in the block) is the program.
                rest = s[len("program:"):].strip()
                if rest:
                    program_text = _dedent_program([rest])
                    i += 1
                else:
                    program_text = _dedent_program(blk[i + 1:])
                    i = len(blk)
            else:
                i += 1

        tasks[tid] = Task(
            id=tid,
            prompts=prompts,
            program_text=program_text,
            state_change=state_change,
            comes_only_after=coa,
            rescan=rescan,
        )

    return TaskFile(answers=answers, tasks=tasks, answer_ids=answer_ids)


if __name__ == "__main__":
    tf = load_task_file()
    print("answers:", len(tf.answers))
    print("tasks:", len(tf.tasks))
    canthelp = [t for t in tf.tasks.values() if t.is_canthelp]
    print("canthelp:", len(canthelp), "actionable:", len(tf.tasks) - len(canthelp))
    for tid in (1, 5, 20, 57):
        t = tf.tasks[tid]
        print("\n==== task", tid, "prompts:", t.prompts, "sc:", t.state_change,
              "coa:", [(c.name, c.args) for c in t.comes_only_after])
        print(t.program_text)
