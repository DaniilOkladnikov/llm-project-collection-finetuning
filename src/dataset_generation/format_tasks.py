"""Format tasks.yaml:

1. Move all `canthelp` tasks to the end (after every other task).
2. Renumber the tasks sequentially (fixes any missing/duplicate indices).
3. Append `[1]` to every answer line inside a task's program.

The script rewrites tasks.yaml in place. Run:  python format_tasks.py
"""

import re
from pathlib import Path

PATH = Path(__file__).with_name("tasks.yaml")

# ---- regexes for the answer lines inside a program -----------------------

# Whole program on one line, e.g.  "answer_1: canthelp"  /  "answer_1: got(X)"
SINGLE_QUOTED = re.compile(r'^(\s*)"(\s*answer_\d+:\s*.*?)"\s*$')
# Bare  "canthelp"  program (tasks 51, 57, 65-69, ...)
CANTHELP_QUOTED = re.compile(r'^(\s*)"canthelp"\s*$')
# Answer header with no inline value ->  answer_1:  /  "answer_1":  /  answer_3:<spaces>
ANSWER_HEADER = re.compile(r'^(\s*)"?answer_\d+"?:\s*$')
# Answer with an inline value ->  answer_2: picked(X, loc)
ANSWER_INLINE = re.compile(r'^(\s*)answer_\d+:\s*\S.*$')
# A branch line that carries the answer value ->  if X in A: thereis(X,A)
BRANCH = re.compile(r'^(\s*)(?:if|elif|else)\b.*?:\s*\S.*$')


def _split_comment(code):
    """Separate a trailing ``# ...`` comment (predicates never contain '#')."""
    idx = code.find("#")
    if idx == -1:
        return code, ""
    return code[:idx].rstrip(), code[idx:]


def _append_one(line):
    """Append ` [1]`, placing it before a trailing delimiter quote / comment.

    A lone trailing `"` (odd count on the line) is the program-string delimiter,
    so `[1]` goes *inside* it. Quoted values like `"holding(X)"` come in pairs
    (even count), so `[1]` goes after them.
    """
    code, comment = _split_comment(line.rstrip())
    core = code.rstrip()
    if core.endswith('"') and core.count('"') % 2 == 1:
        new_core = core[:-1].rstrip() + ' [1]"'
    else:
        new_core = core + " [1]"
    return new_core + (" " + comment if comment else "")


def _process_program(block_lines):
    """Add `[1]` to every answer line in one task block (header kept as-is)."""
    out = [block_lines[0]]  # the `  N:` header line
    in_answer_block = False
    for line in block_lines[1:]:
        m = SINGLE_QUOTED.match(line)
        if m:
            out.append(f'{m.group(1)}"{m.group(2).strip()} [1]"')
            in_answer_block = False
            continue
        m = CANTHELP_QUOTED.match(line)
        if m:
            out.append(f'{m.group(1)}"canthelp [1]"')
            in_answer_block = False
            continue
        if ANSWER_HEADER.match(line):
            out.append(line)          # block answer header, value on next lines
            in_answer_block = True
            continue
        if ANSWER_INLINE.match(line):
            out.append(_append_one(line))
            in_answer_block = False
            continue
        if in_answer_block and BRANCH.match(line):
            out.append(_append_one(line))
            continue                  # stay in block for further elif/else
        out.append(line)
        in_answer_block = False
    return out


def main():
    lines = PATH.read_text(encoding="utf-8").splitlines()

    tasks_idx = next(i for i, l in enumerate(lines) if l.rstrip() == "tasks:")
    head = lines[: tasks_idx + 1]
    body = lines[tasks_idx + 1 :]

    header_re = re.compile(r"^  (\d+):\s*$")
    blocks, cur, pre = [], None, []
    for l in body:
        m = header_re.match(l)
        if m:
            if cur is not None:
                blocks.append(cur)
            cur = [int(m.group(1)), [l]]
        elif cur is None:
            pre.append(l)
        else:
            cur[1].append(l)
    if cur is not None:
        blocks.append(cur)

    # add [1] to the answer lines of every block
    blocks = [[num, _process_program(blk)] for num, blk in blocks]

    def is_canthelp(blk):
        return any("canthelp" in l for l in blk)

    non_canthelp = [b for b in blocks if not is_canthelp(b[1])]
    canthelp = [b for b in blocks if is_canthelp(b[1])]
    ordered = non_canthelp + canthelp

    out = list(head) + pre
    for new_num, (_old, blk) in enumerate(ordered, start=1):
        blk[0] = f"  {new_num}:"          # renumber the header line
        out.extend(blk)

    PATH.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"tasks total   : {len(ordered)}")
    print(f"  actionable  : {len(non_canthelp)}")
    print(f"  canthelp    : {len(canthelp)}")
    print(f"renumbered 1..{len(ordered)}; canthelp moved to the end.")


if __name__ == "__main__":
    main()
