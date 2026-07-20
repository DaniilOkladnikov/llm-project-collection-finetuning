"""Bump the trailing answer marker `[1]` -> `[2]`.

Every answer line inside a task's program ends with a `[N]` marker, e.g.

    answer_2: released [1]        ->  answer_2: released [2]

This applies to every answer line *except* `canthelp` answers, which keep
their `[1]`. The marker is always the last token on the line (optionally
followed by the program-string delimiter `"` and/or a `# comment`), so a
single trailing-position regex covers inline answers, block-answer branch
lines, and whole-line quoted programs alike.

The script rewrites tasks.yaml in place. Run:  python bump_marker.py
"""

import re
from pathlib import Path

PATH = Path(__file__).with_name("tasks.yaml")

# `[1]` as the trailing marker: only a closing quote, whitespace and/or a
# trailing comment may follow it on the line.
MARKER = re.compile(r'\[1\](?=\s*"?\s*(?:#.*)?$)')


def main():
    lines = PATH.read_text(encoding="utf-8").splitlines()

    changed = skipped = 0
    out = []
    for line in lines:
        if MARKER.search(line):
            if "canthelp" in line:
                skipped += 1
            else:
                line = MARKER.sub("[2]", line)
                changed += 1
        out.append(line)

    PATH.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"answer markers bumped [1] -> [2] : {changed}")
    print(f"canthelp answers left at [1]     : {skipped}")


if __name__ == "__main__":
    main()
