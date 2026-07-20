"""Resolve a task's prompt variables (X, W, A, B, C, P) against a scene.

Rules (from the spec):
* X, W  -> object *types* (distinct).
* A, B, C -> targets: a location-name collection or a single location. All
  chosen targets are pairwise disjoint (no shared location), and are all
  different.
* P -> any position in the scene.
* ``loc`` is an internal program variable, never a prompt binding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from gen.scene_model import SceneModel

_TOKENS = ("A", "B", "C", "X", "W", "P")
_TOKEN_RE = re.compile(r"(?<![\w{])(A|B|C|X|W|P)(?![\w}])")


def used_tokens(prompt: str, program_text: str) -> List[str]:
    found = set()
    for text in (prompt, program_text):
        for m in _TOKEN_RE.finditer(text.replace("{", " ").replace("}", " ")):
            found.add(m.group(1))
    return [t for t in _TOKENS if t in found]


@dataclass
class Binding:
    types: Dict[str, str] = field(default_factory=dict)      # X/W -> type
    phrases: Dict[str, str] = field(default_factory=dict)    # A/B/C/X/W/P -> phrase
    locs: Dict[str, List[str]] = field(default_factory=dict)  # A/B/C -> [loc]
    p_position: Optional[str] = None

    def parse_user_delta(self) -> dict:
        d = {}
        for t in ("A", "B", "C"):
            if t in self.locs:
                d[self.phrases[t]] = "[" + ", ".join(f'"{l}"' for l in self.locs[t]) + "]"
        return d


def _target_candidates(scene: SceneModel, prefer_collections: bool, rng):
    cols = [(name, scene.order(locs)) for name, locs in scene.location_names.items()]
    singles = [(loc, [loc]) for loc in scene.canonical_order]
    rng.shuffle(cols)
    rng.shuffle(singles)
    if prefer_collections:
        return cols + singles
    pool = cols + singles
    rng.shuffle(pool)
    return pool


def sample_bindings(scene: SceneModel, tokens: List[str], rng,
                    prefer_collections: bool = True,
                    single_targets: bool = False) -> Optional[Binding]:
    b = Binding()

    # --- targets A, B, C first (pairwise disjoint) -------------------------
    need_targets = [t for t in ("A", "B", "C") if t in tokens]
    if need_targets:
        if single_targets:
            cands = [(loc, [loc]) for loc in scene.canonical_order]
            rng.shuffle(cands)
        else:
            cands = _target_candidates(scene, prefer_collections, rng)
        used_locs: set = set()
        picked = []
        for name, locs in cands:
            if len(picked) >= len(need_targets):
                break
            if set(locs) & used_locs:
                continue
            if any(name == p[0] for p in picked):
                continue
            picked.append((name, locs))
            used_locs |= set(locs)
        if len(picked) < len(need_targets):
            return None
        for tok, (name, locs) in zip(need_targets, picked):
            b.phrases[tok] = name
            b.locs[tok] = locs

    # --- object types, constrained to be placeable in the targets ----------
    def placeable_in(locs):
        s = set()
        for l in locs:
            s |= set(scene.placeable_types_at(l))
        return s

    need_types = [t for t in ("X", "W") if t in tokens]
    if need_types:
        # X should be placeable in A (if A present); W in A or B.
        pref_X = placeable_in(b.locs.get("A", [])) if "A" in b.locs else set()
        pref_W = pref_X | placeable_in(b.locs.get("B", [])) if b.locs else set()
        pool = scene.pickable_types or list(scene.object_types)
        chosen = {}
        order = need_types
        prefer = {"X": pref_X, "W": pref_W or pref_X}
        for tok in order:
            cand = [t for t in (prefer.get(tok) or pool)
                    if t not in chosen.values()]
            if not cand:
                cand = [t for t in pool if t not in chosen.values()]
            if not cand:
                return None
            chosen[tok] = rng.choice(cand)
        for tok, ty in chosen.items():
            b.types[tok] = ty
            b.phrases[tok] = ty

    # --- position P --------------------------------------------------------
    if "P" in tokens:
        p = rng.choice(scene.position_names)
        b.p_position = p
        b.phrases["P"] = p

    return b
