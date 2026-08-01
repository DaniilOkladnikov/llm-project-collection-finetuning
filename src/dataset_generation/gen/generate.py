"""Dataset generator: drive random scenes + back-solved states through the DSL
interpreter until every task answer is covered its required number of times.

Usage:  uv run generate.py  [--out dataset.json] [--seed 0] [--limit N]
        (equivalently: python -m gen.generate ...)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Make this runnable directly (`uv run generate.py`, from any cwd): put the
# package's parent dir (src/dataset_generation) on sys.path so that both the
# `gen.*` modules and the sibling `scene_generator` module resolve.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from gen.taskfile import load_task_file, Task
from gen.program import parse_program, Program, Answer, IfChain, substitute
from gen.answers import AnswerResolver
from gen.scene_model import SceneModel
from gen.interpreter import Executor, ModelState, Invalid
from gen.conversation import Conversation
from gen.bindings import used_tokens, sample_bindings, Binding

import scene_generator


# --- targets ----------------------------------------------------------------

@dataclass
class Target:
    task_id: int
    label: str
    branch_idx: int
    macro: str
    count: int

    @property
    def key(self) -> Tuple[int, str, int]:
        return (self.task_id, self.label, self.branch_idx)


# Structural dead-ends in the task programs themselves (with terminating-ANSWER
# semantics, which task 1's gripper-closed path requires). Documented per the
# spec's requirement to record unreachable answers.
UNREACHABLE_REASONS = {
    (11, "answer_2"): "program does `go to pick MEMORY.scans[loc] from loc` where "
                      "loc is an empty slot; there is no pick pose for type 'empty'.",
    (19, "answer_3"): "`place in loc` targets loc = first NON-empty slot of B, i.e. "
                      "placing into an occupied slot (invalid).",
    (21, "answer_3"): "`where value is not W` also matches empty slots, so loc is "
                      "never None while A is empty -> isempty branch never taken.",
    (26, "answer_1"): "donthold needs gripper open, but the required prior `picked` "
                      "leaves the gripper closed.",
    (26, "answer_2"): "`place in loc` where loc must already hold X (scans==X): "
                      "placing into an occupied slot (invalid).",
    (53, "answer_3"): "dead code: answer_1/answer_2 emitted earlier terminate the turn.",
    (53, "answer_4"): "dead code: answer_1/answer_2 emitted earlier terminate the turn.",
    (55, "answer_5"): "dead code: an earlier answer terminates the turn.",
    (55, "answer_6"): "dead code: an earlier answer terminates the turn.",
    (70, "answer_3"): "dead code: answer_1/answer_2 emitted earlier terminate the turn.",
    (70, "answer_4"): "dead code: answer_1/answer_2 emitted earlier terminate the turn.",
}


def _macro_name(macro_text: str) -> str:
    m = re.match(r"\s*([A-Za-z_]\w*)", macro_text or "")
    return m.group(1) if m else ""


def _iter_answers(nodes):
    for n in nodes:
        if isinstance(n, IfChain):
            for b in n.branches:
                yield from _iter_answers(b.body)
        elif isinstance(n, Answer):
            yield n


def enumerate_targets(tf, progs) -> List[Target]:
    out = []
    for tid, task in tf.tasks.items():
        prog = progs[tid]
        for a in _iter_answers(prog.body):
            if a.selection:
                for idx, (_c, macro, cnt) in enumerate(a.selection):
                    out.append(Target(tid, a.label, idx, macro, cnt))
            else:
                out.append(Target(tid, a.label, -1, a.macro, a.count))
    return out


# --- state sampling ---------------------------------------------------------

OCC_MODES = ["random", "X_in_A", "A_empty", "A_full", "full", "empty", "no_X",
             "dense", "sparse"]
GRIP_MODES = ["open", "closed_hold", "closed_unknown"]


def modes_for(macro: str) -> List[str]:
    m = macro or ""
    if any(k in m for k in ("isfull", "nospace2place", "notfull", "neitherempty",
                            "atleastonenonempty")):
        pri = ["full", "A_full", "dense", "random"]
    elif "thereisno" in m and "[A]" not in m and "[A," not in m:
        pri = ["no_X", "empty", "random"]
    elif any(k in m for k in ("isempty", "donthold", "atleastoneempty")):
        pri = ["empty", "A_empty", "sparse", "no_X", "random"]
    elif any(k in m for k in ("picked", "placed", "thereis", "locof", "canpick",
                              "isnonempty", "gotfrom", "firstemptyat", "lastpicked",
                              "thereisonly", "nameobjects", "projectedafter")):
        pri = ["X_in_A", "random", "dense", "A_full"]
    else:
        pri = ["random", "X_in_A", "A_empty", "A_full", "dense", "sparse"]
    seen, out = set(), []
    for x in pri + OCC_MODES:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _rand_type_at(scene: SceneModel, loc: str, rng, exclude=()):
    opts = [t for t in scene.placeable_types_at(loc) if t not in exclude]
    return rng.choice(opts) if opts else None


def apply_state(scene: SceneModel, occ_mode: str, grip_mode: str,
                binding: Binding, statechange: dict, rng) -> dict:
    tX = binding.types.get("X")
    A_locs = binding.locs.get("A", [])
    occ = {loc: None for loc in scene.canonical_order}
    prob = {"random": 0.5, "sparse": 0.25, "dense": 0.8, "no_X": 0.5,
            "X_in_A": 0.5, "A_empty": 0.5, "A_full": 0.6, "full": 1.0, "empty": 0.0}
    p = prob.get(occ_mode, 0.5)
    excl = (tX,) if occ_mode == "no_X" and tX else ()
    for loc in scene.canonical_order:
        if rng.random() < p:
            occ[loc] = _rand_type_at(scene, loc, rng, exclude=excl)
    if occ_mode == "full":
        for loc in scene.canonical_order:
            occ[loc] = _rand_type_at(scene, loc, rng) or occ[loc]
    if occ_mode == "X_in_A" and tX and A_locs:
        cand = [l for l in A_locs if tX in scene.placeable_types_at(l)]
        if cand:
            occ[rng.choice(cand)] = tX
    if occ_mode == "A_empty":
        for l in A_locs:
            occ[l] = None
    if occ_mode == "A_full":
        for l in A_locs:
            occ[l] = _rand_type_at(scene, l, rng) or occ[l]
    scene.set_occupancy(occ)

    # place feasibility: if we are holding a type T, then for each place target
    # make its first empty slot one that actually supports placing T (so the
    # program's "first empty in <target>" resolves to a placeable slot).
    held_T = None
    if statechange and statechange.get("gripper") == "closed":
        held_T = statechange.get("held")
    if held_T and occ_mode != "full" and rng.random() < 0.7:
        for tok in ("A", "B", "C"):
            tlocs = binding.locs.get(tok)
            if not tlocs:
                continue
            support = [l for l in scene.order(tlocs) if scene.place_pos(held_T, l)]
            if support:
                L = support[0]
                for l in scene.order(tlocs):
                    if l == L:
                        break
                    if occ.get(l) is None:
                        occ[l] = _rand_type_at(scene, l, rng) or occ.get(l)
                occ[L] = None
        scene.set_occupancy(occ)

    # gripper / held
    if statechange:
        closed = statechange.get("gripper") == "closed"
        scene.gripper_open = not closed
        scene.held = statechange.get("held") if closed else None
    elif grip_mode == "open":
        scene.gripper_open = True
        scene.held = None
    else:  # closed_hold / closed_unknown
        scene.gripper_open = False
        types = scene.pickable_types or list(scene.object_types)
        scene.held = rng.choice(types) if types else None
    scene.robot_position = scene.home() or scene.robot_position
    return scene.truth_snapshot()


def resolve_statechange(task: Task, binding: Binding) -> dict:
    if not task.state_change:
        return {}
    out = {}
    for k, v in task.state_change.items():
        if k == "held":
            out["held"] = binding.types.get(v, v)
        else:
            out[k] = v
    if "gripper" not in out:
        out["gripper"] = "closed"
    return out


# --- prompt rendering -------------------------------------------------------

def render_prompt(template: str, binding: Binding) -> str:
    subst = {}
    subst.update({k: v for k, v in binding.types.items()})
    for t in ("A", "B", "C", "P"):
        if t in binding.phrases:
            subst[t] = binding.phrases[t]
    text = substitute(template, subst)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()


# --- the generator ----------------------------------------------------------

class Generator:
    def __init__(self, seed: int = 0, out_path: str = None):
        self.tf = load_task_file()
        self.resolver = AnswerResolver(self.tf.answers)
        self.rng = random.Random(seed)
        self.progs: Dict[int, Program] = {
            tid: parse_program(t.program_text) for tid, t in self.tf.tasks.items()}
        self.targets = enumerate_targets(self.tf, self.progs)
        self.remaining: Dict[tuple, int] = {t.key: t.count for t in self.targets}
        self.target_by_key = {t.key: t for t in self.targets}
        self.dataset: "OrderedDict[int, dict]" = OrderedDict()
        self.next_id = 0
        self.conv_id = 0
        self.unreachable: List[dict] = []
        if out_path:
            self.out_path = out_path
        else:
            stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            self.out_path = os.path.join(_HERE, f"dataset_{stamp}.json")
        self._scene = None
        self._scene_uses = 0
        self._convs_since_save = 0

    # --- scene pool --------------------------------------------------------

    def fresh_scene(self) -> SceneModel:
        return SceneModel(scene_generator.generate_scene(self.rng))

    def scene(self, force_new=False) -> SceneModel:
        if self._scene is None or self._scene_uses > 30 or force_new:
            self._scene = self.fresh_scene()
            self._scene_uses = 0
        self._scene_uses += 1
        return self._scene

    # --- trials ------------------------------------------------------------

    def _run_seq(self, scene: SceneModel, specs) -> Optional[Tuple[list, list]]:
        """Run a sequence of (task, prog, binding, statechange) through fresh
        executors carrying ModelState. Returns (targets, exs) or None."""
        st = ModelState()
        targets, exs = [], []
        for (task, prog, binding, sc) in specs:
            for k, v in sc.items():
                if k == "gripper":
                    st.gripper = v
                elif k == "held":
                    st.held = v
            ex = Executor(scene, st, self.resolver, task.id, binding.types,
                          binding.phrases, binding.locs, binding.p_position)
            try:
                ex.run(prog)
            except Invalid:
                return None
            if not ex.steps or ex.steps[-1].kind != "answer":
                return None
            targets.append(ex.steps[-1].target)
            exs.append(ex)
            st.parsed = True
        return targets, exs

    # --- single-turn coverage ---------------------------------------------

    def cover_single(self, target: Target, budget: int) -> Optional[Conversation]:
        task = self.tf.tasks[target.task_id]
        prog = self.progs[target.task_id]
        modes = modes_for(target.macro)
        for attempt in range(budget):
            scene = self.scene(force_new=(attempt % 20 == 0 and attempt > 0))
            template = self.rng.choice(task.prompts)
            tokens = used_tokens(template, task.program_text)
            binding = sample_bindings(scene, tokens, self.rng,
                                      prefer_collections=self.rng.random() < 0.6,
                                      single_targets=self.rng.random() < 0.3)
            if binding is None:
                continue
            sc = resolve_statechange(task, binding)
            occ_mode = modes[0] if attempt < 3 else self.rng.choice(modes[:5] + OCC_MODES)
            grip_mode = self.rng.choice(GRIP_MODES)
            setup = apply_state(scene, occ_mode, grip_mode, binding, sc, self.rng)
            res = self._run_seq(scene, [(task, prog, binding, sc)])
            scene.restore(setup)
            if res is None:
                continue
            targets, _exs = res
            if targets[-1] and targets[-1][:3] == target.key:
                return self._render([(task, prog, binding, sc,
                                      render_prompt(template, binding))], scene, setup)
        return None

    # --- multi-turn (primers + comes-only-after) --------------------------

    def cover_multi(self, target: Target, budget: int) -> Optional[Conversation]:
        task = self.tf.tasks[target.task_id]
        plans = self._plans_for(target)
        per = max(30, budget // max(1, len(plans)))
        for plan in plans:
            for attempt in range(per):
                scene = self.scene(force_new=(attempt % 15 == 0 and attempt > 0))
                specs = self._build_plan(plan, target, scene)
                if specs is None:
                    continue
                specs, prompts, setup = specs
                res = self._run_seq(scene, specs)
                scene.restore(setup)
                if res is None:
                    continue
                targets, _exs = res
                if targets[-1] and targets[-1][:3] == target.key:
                    render_specs = [(s[0], s[1], s[2], s[3], p)
                                    for s, p in zip(specs, prompts)]
                    return self._render(render_specs, scene, setup)
        return None

    def _plans_for(self, target: Target) -> List[List[str]]:
        task = self.tf.tasks[target.task_id]
        if task.comes_only_after:
            return [["coa"]]
        return [["held"], ["position"], ["held", "release"]]

    def _build_plan(self, plan, target, scene):
        """Return (specs, prompts, setup) for a multi-turn plan or None."""
        task = self.tf.tasks[target.task_id]
        prog = self.progs[target.task_id]
        rng = self.rng

        if plan == ["coa"]:
            return self._build_coa(target, scene)

        # target turn binding first, so primers can be coordinated to it.
        template = rng.choice(task.prompts)
        tokens = used_tokens(template, task.program_text)
        tb = sample_bindings(scene, tokens, rng,
                             prefer_collections=rng.random() < 0.6,
                             single_targets=rng.random() < 0.3)
        if tb is None:
            return None
        sc = resolve_statechange(task, tb)

        # the held type the primer should provide: placeable in the target's A
        held_type = None
        if "A" in tb.locs:
            supp = sorted({t for l in tb.locs["A"] for t in scene.placeable_types_at(l)})
            if supp:
                held_type = rng.choice(supp)

        specs, prompts = [], []
        for p in plan:
            if p == "held":
                t2 = self.tf.tasks[2]
                b = Binding()
                ht = held_type or rng.choice(scene.pickable_types or ["object"])
                b.types["X"] = ht
                b.phrases["X"] = ht
                specs.append((t2, self.progs[2], b, {}))
                prompts.append(render_prompt(rng.choice(t2.prompts), b))
            elif p == "release":
                t3 = self.tf.tasks[3]
                specs.append((t3, self.progs[3], Binding(), {}))
                prompts.append(rng.choice(t3.prompts))
            elif p == "position":
                t8 = self.tf.tasks[8]
                b = sample_bindings(scene, ["P"], rng)
                if b is None:
                    return None
                if rng.random() < 0.5 and scene.home():   # sometimes target home
                    b.p_position = scene.home()
                    b.phrases["P"] = scene.home()
                specs.append((t8, self.progs[8], b, {}))
                prompts.append(render_prompt(rng.choice(t8.prompts), b))

        specs.append((task, prog, tb, sc))
        prompts.append(render_prompt(template, tb))

        # gripper open at start (so held primer works); occupancy tuned, and if the
        # target places into A make the first empty A slot support the held type.
        _mm = modes_for(target.macro)
        occ_mode = rng.choice(_mm[:4] + OCC_MODES)
        fake_sc = {"gripper": "closed", "held": held_type} if held_type else {}
        setup = apply_state(scene, occ_mode, "open", tb, fake_sc, rng)
        # but we actually START gripper open (primer will close it)
        scene.gripper_open = True
        scene.held = None
        setup = scene.truth_snapshot()
        return specs, prompts, setup

    def _build_coa(self, target, scene):
        """comes-only-after: run a primer that *verifiably* yields the qualifying
        answer (binding X and A), then the target task inheriting X / A / loc."""
        task = self.tf.tasks[target.task_id]
        prog = self.progs[target.task_id]
        rng = self.rng
        coa_names = {s.name for s in task.comes_only_after}

        # clean primers: each binds X and A and can produce the named macro.
        if "picked" in coa_names:
            pid, occ_choices = 1, ["X_in_A"]
        elif "locof" in coa_names and "thereis" not in coa_names:
            pid, occ_choices = 16, ["X_in_A"]
        else:  # thereis / thereisno (task 71) or thereis+locof (task 83)
            pid = rng.choice([14, 16]) if "locof" in coa_names else 14
            occ_choices = ["X_in_A", "no_X", "empty"]

        ptask = self.tf.tasks[pid]
        pprog = self.progs[pid]
        ptemplate = rng.choice(ptask.prompts)
        ptokens = used_tokens(ptemplate, ptask.program_text)
        pb = sample_bindings(scene, ptokens, rng, prefer_collections=True)
        if pb is None:
            return None
        psc = resolve_statechange(ptask, pb)

        setup = apply_state(scene, rng.choice(occ_choices), "open", pb, psc, rng)

        # run primer alone; require its answer to satisfy the coa constraint.
        res = self._run_seq(scene, [(ptask, pprog, pb, psc)])
        scene.restore(setup)
        if res is None:
            return None
        ptarget, pex = res[0][0], res[1][0]
        if not ptarget or ptarget[3] and _macro_name(ptarget[3]) not in coa_names:
            return None

        # inherit bindings; find the location X sits at in A (for loc-based answers)
        tb = Binding()
        tb.types = dict(pb.types)
        tb.phrases = dict(pb.phrases)
        tb.locs = dict(pb.locs)
        xtype = pb.types.get("X")
        a_locs = pb.locs.get("A", [])
        loc = pex.st.vars.get("loc")
        if loc is None and xtype:
            for l in a_locs:
                if pex.st.scans.get(l) == xtype:
                    loc = l
                    break

        # task 26 ("put it back where you got it"): A is that single location
        if task.id == 26 and loc:
            tb.locs["A"] = [loc]
            tb.phrases["A"] = "where you got it"

        template = rng.choice(task.prompts)
        specs = [(ptask, pprog, pb, psc),
                 (task, prog, tb, resolve_statechange(task, tb))]
        prompts = [render_prompt(ptemplate, pb), render_prompt(template, tb)]
        return specs, prompts, setup

    # --- render + commit ---------------------------------------------------

    def _render(self, render_specs, scene, setup) -> Conversation:
        scene.restore(setup)
        conv = Conversation(scene, self.resolver, self.conv_id)
        for i, (task, prog, binding, sc, prompt) in enumerate(render_specs):
            conv.add_turn(task, prog, prompt, binding.types, binding.phrases,
                          binding.locs, binding.p_position, binding.parse_user_delta(),
                          sc, first_turn=(i == 0))
        return conv

    def _maybe_extend(self, conv: Conversation):
        """Append 0-2 further valid turns that accept the carried state, so
        conversations span 1-3 turns as specified. Extra turns never use a
        state-change (turns 2+ accept whatever state the prior turn left) and
        never a comes-only-after task (those need a specific qualifying prior)."""
        rng = self.rng
        n_extra = rng.choices([0, 1, 2], weights=[0.45, 0.4, 0.15])[0]
        n_extra = min(n_extra, 3 - len(conv.turns))   # conversations span 1-3 turns
        if n_extra <= 0:
            return
        scene = conv.scene
        cand_ids = [tid for tid, t in self.tf.tasks.items()
                    if not t.comes_only_after and not t.state_change]
        for _ in range(n_extra):
            rng.shuffle(cand_ids)
            appended = False
            for tid in cand_ids[:30]:
                task = self.tf.tasks[tid]
                prog = self.progs[tid]
                template = rng.choice(task.prompts)
                tokens = used_tokens(template, task.program_text)
                b = sample_bindings(scene, tokens, rng,
                                    prefer_collections=rng.random() < 0.6,
                                    single_targets=rng.random() < 0.3)
                if b is None:
                    continue
                snap = scene.truth_snapshot()
                st = conv.state.copy()
                ex = Executor(scene, st, self.resolver, tid, b.types, b.phrases,
                              b.locs, b.p_position)
                try:
                    ex.run(prog)
                    ok = bool(ex.steps) and ex.steps[-1].kind == "answer"
                except Invalid:
                    ok = False
                scene.restore(snap)
                if not ok:
                    continue
                conv.add_turn(task, prog, render_prompt(template, b), b.types,
                              b.phrases, b.locs, b.p_position, b.parse_user_delta(),
                              {}, first_turn=False)
                appended = True
                break
            if not appended:
                break

    def commit(self, conv: Conversation):
        for turn in conv.turns:
            tgt = turn.get("target")
            if tgt and tgt[:3] in self.remaining and self.remaining[tgt[:3]] > 0:
                self.remaining[tgt[:3]] -= 1
        for seq, inv in enumerate(conv.invocations):
            self.dataset[self.next_id] = {
                "input": inv["input"],
                "output": inv["output"],
                "metadata": {
                    "conversation_id": conv.conv_id,
                    "index_in_conversation": seq,
                    "task_id": inv.get("task_id"),
                    "prompt": inv.get("prompt"),
                    "answer": inv.get("answer"),
                },
            }
            self.next_id += 1
        self.conv_id += 1
        self._convs_since_save += 1
        if self._convs_since_save >= 100:
            self.save()
            self._convs_since_save = 0

    # --- driver ------------------------------------------------------------

    def run(self, limit: Optional[int] = None):
        targets = list(self.targets)
        # hard (global-state) answers first, so their dedicated back-solving runs
        # before the scene pool warms up.
        def hardness(t):
            m = t.macro or ""
            if "thereisno" in m and "[A" not in m:
                return 0
            if any(k in m for k in ("isfull", "nospace2place", "isempty")):
                return 1
            return 2
        targets.sort(key=hardness)

        total = len(targets)
        start = time.time()
        for i, target in enumerate(targets):
            if limit and self.conv_id >= limit:
                break
            task = self.tf.tasks[target.task_id]
            need = self.remaining[target.key]      # full required count (pre-run)
            # Keep back-solving conversations for this target until its required
            # count is satisfied. Each successful conversation covers it >=1 time
            # (its final turn), plus any incidental coverings from primers/extras;
            # a failed attempt means we can't reach the count and we stop trying.
            while self.remaining[target.key] > 0:
                if limit and self.conv_id >= limit:
                    break
                conv = None
                if not task.comes_only_after:
                    conv = self.cover_single(target, budget=200)
                if conv is None:
                    conv = self.cover_multi(target, budget=300)
                if conv is None:
                    covered_any = self.remaining[target.key] < need
                    if not covered_any:
                        # never reached even once -> structurally unreachable
                        reason = UNREACHABLE_REASONS.get(
                            (target.task_id, target.label),
                            "no scene/state found in the attempt budget (see spec: "
                            "may be structurally unreachable).")
                        self.unreachable.append({
                            "task_id": target.task_id, "label": target.label,
                            "branch": target.branch_idx, "macro": target.macro,
                            "reason": reason})
                        print(f"  [UNREACHABLE] task {target.task_id} "
                              f"{target.label} ({target.macro})")
                    else:
                        # covered at least once but couldn't hit the full count
                        print(f"  [PARTIAL] task {target.task_id} {target.label} "
                              f"({target.macro}) covered "
                              f"{need - self.remaining[target.key]}/{need}")
                    self.remaining[target.key] = 0
                    break
                self._maybe_extend(conv)
                self.commit(conv)
            done = sum(1 for t in self.targets if self.remaining[t.key] <= 0)
            if (i + 1) % 10 == 0 or i + 1 == total:
                el = time.time() - start
                print(f"[{i+1}/{total}] covered={done}/{total} convs={self.conv_id} "
                      f"elements={self.next_id} unreachable={len(self.unreachable)} "
                      f"({el:.0f}s)")
        self.save()
        self._report()

    def save(self):
        with open(self.out_path, "w", encoding="utf-8") as fh:
            json.dump(self.dataset, fh, ensure_ascii=False, indent=1)
        meta_path = self.out_path.replace(".json", "_report.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump({"unreachable": self.unreachable,
                       "conversations": self.conv_id,
                       "elements": self.next_id}, fh, ensure_ascii=False, indent=1)

    def _report(self):
        done = sum(1 for t in self.targets if self.remaining[t.key] <= 0)
        print("\n===== DONE =====")
        print(f"targets covered : {done}/{len(self.targets)}")
        print(f"conversations   : {self.conv_id}")
        print(f"dataset elements: {self.next_id}")
        print(f"unreachable     : {len(self.unreachable)}")
        print(f"written to      : {self.out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    gen = Generator(seed=args.seed, out_path=args.out)
    gen.run(limit=args.limit)


if __name__ == "__main__":
    main()
