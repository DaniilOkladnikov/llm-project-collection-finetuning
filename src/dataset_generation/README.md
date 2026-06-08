# Pick-and-Place DSL dataset generation

Generates supervised fine-tuning data that teaches an LLM to drive the
pick-and-place robot using the block DSL in [DSL.md](DSL.md). For every task in
[Tasks.md](Tasks.md), across every scene in `tool-simulation-server/scenes/`, the
task program is executed step-by-step against the **real (headless) simulator**,
emitting every block exactly as the context-manager loop (DSL §1.5) prescribes.

**Each LLM invocation (one forward pass) is one dataset entry** —
`{"input": <text fed to the model>, "output": <blocks the model emits>, "metadata": {...}}` —
full fidelity, including the trivial `CHECK` passes after every tool call.

## Run

```bash
# full cross-product: all tasks x all scenes x 3
python -m dataset_generation.generate

# smoke run
python -m dataset_generation.generate --scenes scene_box_11_cube,scene_binA_001_gear --cap 400
```

Output: `dataset_generation/datasets/dataset_<YYYYMMDD_HHMMSS>.json`.

## How it works

1. **Resolve** (`resolve.py`): bind `$X`/`$W` (object types) and `$A`/`$B`
   (locations or collections) to the scene via
   `finetuning.variable_resolver.VariableResolver`; skip task/scene pairs whose
   pick/place/observe coverage can't be satisfied.
2. **Seed state** (`resolve.py` + `tool_simulation_server.state_resolver`): random
   objects (0..max) and robot pose; for "holding" tasks the held object is
   attached and the gripper closed.
3. **Execute** (`interpreter.py`): walk the DSL §1.5 loop, calling the 7 robot
   tools directly on a headless `Simulation` (`sim_driver.py`) — no HTTP/MCP — so
   tool results are ground truth. One `{input, output}` entry per invocation.

## Modules

| file | role |
|------|------|
| `sim_driver.py` | headless `Simulation` + the 7-tool DSL surface (`{status, content}` envelope) |
| `dsl_state.py`  | model-side STATE (cursor/position/gripper/held/scans/visited/memory) + §3.1 effects |
| `helpers.py`    | ObjectType/Location helpers (§5.6/5.7) + condition expressions (§5.8) |
| `program.py`    | `Program`/`Step`/`Arm`/`Primitive`; resolution → RESOLUTION lines + TOOLS |
| `context.py`    | `SceneView` (slot order, observe coverage, pose lookup) + role binding |
| `blocks.py`     | renders every block to text (MAP/STATE/PROGRAM/RESOLUTION/TOOLS/…/ANSWER) |
| `interpreter.py`| the context-manager loop; assembles I1/I2/I3 inputs, emits O1..O6 outputs |
| `taskspec.py`   | `TaskSpec` + `AnswerEnv` (answer-prose helpers) |
| `tasks.py`      | all Tasks.md entries transcribed into executable `TaskSpec`s |
| `resolve.py`    | per-(task, scene) binding, compatibility gates, random initial state |
| `generate.py`   | driver over scenes × tasks × N; saves the dataset |

## Notes

- Programs are in DSL block form: one branching per step; early-exit guards are
  single-arm `when` steps that fall through (cursor advances) when false (§5.3).
- Within-step values use `temp`; cross-step values use `remember` (turn memory).
- Resolution forward-predicts deterministic tool effects (move/pick/place) so a
  `pick; place` step resolves `X = held` correctly before tools run.
- A few obvious logic typos in Tasks.md answer conditions (e.g. "Are there any
  empty slots in A?") are corrected; the answer wording is kept verbatim.
