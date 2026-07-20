# Pick-and-place DSL dataset generator

A deterministic DSL interpreter that turns the tasks in `../tasks.yaml` into a
fine-tuning dataset. It drives **random scenes** from `../scene_generator.py`
through **back-solved states** until every task answer is present at least the
number of times its `[N]` requires, emitting **every model invocation** of every
turn as a separate byte-faithful input/output pair.

## Run

```bash
python -m gen.generate            # writes ../dataset.json + ../dataset_report.json
python -m gen.generate --seed 7 --out mydata.json
python -m gen.generate --limit 50 # cap number of conversations (smoke test)
```

Progress is printed to the terminal; the dataset is saved to disk every 100
conversations and once more at the end. Back-solving for any single answer is
capped at 500 randomized attempts (200 single-turn + 300 multi-turn); if it never
hits, the answer is recorded in `dataset_report.json → unreachable` with a reason
instead of looping forever.

## Output format

`dataset.json` is a dict `{ "<id>": {"input", "output", "metadata"} }`. One entry
per invocation. `metadata` holds `conversation_id`, `index_in_conversation`
(0-based, so a conversation can be reconstructed in order), `task_id`, `prompt`,
`answer`.

## Module map

| module | responsibility |
|--------|----------------|
| `taskfile.py`   | parse `tasks.yaml` (answers macros + tasks; programs are indentation-sensitive pseudo-code, not valid YAML) |
| `program.py`    | parse a program into an AST + render the numbered `PROGRAM` block |
| `answers.py`    | resolve an answer-macro string (f-strings, `. `-compositions, directive macros) to the exact answer text |
| `scene_model.py`| mutable, self-contained mirror of the simulator's *observable* behaviour (positions by structural match, `locate` = occupied observable slots) |
| `bindings.py`   | resolve prompt variables X, W (types), A, B, C (disjoint targets), P (position) |
| `interpreter.py`| the executor: expression/condition evaluation, primitive tool-op sequences, chunking of the turn into invocations |
| `conversation.py`| the context manager: assembles inputs, emits output deltas, carries MEMORY across turns |
| `generate.py`   | the driver: answer accounting, state sampling / back-solvers, multi-turn primers, comes-only-after, saving, progress |

## Semantics honored

* Turn 1 emits the fixed *parse* program (get positions / parse objects / parse
  locations / parse user) first; turns 2–3 skip it (that state is already in
  memory) and fold the new parse-user bindings into the real program's first
  MEMORY delta.
* Turn 1 gets a freely back-solved state; turns 2–3 accept whatever the prior
  turn left (their answer is constrained by that carried state).
* A resolution chunk ends at the first primitive requiring a tool call or a
  memory write; multi-tool primitives are emitted one op at a time.
* `remember key = tool()` appends `key = result` to MEMORY (no `TOOL RESULTS`);
  plain tool calls produce a `TOOL RESULTS` block in the next input.
* Every tool result is wrapped `{status: "OK", content: <value>}`. Tool names are
  `list_avaliable_robot_positions, get_robot_position, get_gripper_state,
  move_robot_to, open_gripper, close_gripper, locate_shapes`.
* Positions are resolved by structural match on the scene's `positions` fields,
  never by string formatting. `scans` is populated for the whole revealed set of
  an observe pose. Canonical "first in" order follows the positions list.

## Back-solvers

The generator hits the globally-constrained answers first (whole scene empty /
full / missing a type) via dedicated occupancy modes (`empty`, `full`, `no_X`,
…), then rejection-samples the rest. Multi-turn *precondition* answers (a known
gripper/held/position, or a `comes only after` qualifier) are produced by
prepending verified primer turns.

## Documented-unreachable answers

A handful of task-program branches are structurally unreachable given
terminating-`ANSWER` semantics (which task 1's gripper-closed path requires) —
e.g. code after an answer that already ends the turn, `place`-into-occupied,
`pick`-from-empty, or a predicate (`not W`) that also matches empty slots. These
are enumerated with reasons in `dataset_report.json`; they are program dead-ends,
not generator gaps.
