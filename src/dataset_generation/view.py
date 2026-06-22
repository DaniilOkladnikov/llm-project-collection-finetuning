"""Dataset viewer: scroll through one conversation's input/output turns.

Loads a dataset produced by ``dataset_generation.generate`` and shows a single
turn (one ``{input, output}`` entry) at a time, nicely formatted. Consecutive
entries sharing ``(task_id, scene, seed)`` form one conversation; you can step
through the turns of a conversation and jump between conversations.

Usage
-----
Newest dataset in ``datasets/``::

    python -m dataset_generation.view

Explicit file::

    python -m dataset_generation.view path/to/dataset_YYYYMMDD_HHMMSS.json

Keys
----
  Left / Right        previous / next turn in the conversation
  Up / Down           previous / next conversation
  Home / End          first / last turn of the conversation
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tkinter as tk
from itertools import groupby
from pathlib import Path
from tkinter import font as tkfont
from typing import Dict, List

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


def newest_dataset() -> Path:
    files = sorted(DATASETS_DIR.glob("dataset_*.json"))
    if not files:
        raise FileNotFoundError(f"No dataset_*.json in {DATASETS_DIR}")
    return files[-1]


def _convo_key(entry: Dict) -> tuple:
    m = entry.get("metadata") or {}
    return (m.get("task_id"), m.get("scene"), m.get("seed"))


def group_conversations(dataset: List[Dict]) -> List[List[Dict]]:
    """Split the flat dataset into conversations of consecutive same-key turns."""
    convos: List[List[Dict]] = []
    for _, turns in groupby(dataset, key=_convo_key):
        convos.append(list(turns))
    return convos


class Viewer(tk.Tk):
    def __init__(self, convos: List[List[Dict]], source: Path):
        super().__init__()
        self.convos = convos
        self.ci = 0  # conversation index
        self.ti = 0  # turn index within conversation

        self.title(f"Dataset viewer — {source.name}")
        self.geometry("1100x780")

        mono = tkfont.nametofont("TkFixedFont").copy()
        mono.configure(size=11)
        header_font = tkfont.Font(size=12, weight="bold")

        # Header / status bar
        self.header = tk.Label(self, anchor="w", justify="left",
                               font=header_font, padx=10, pady=6)
        self.header.pack(side="top", fill="x")

        body = tk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        # Input pane
        in_frame = tk.LabelFrame(body, text="INPUT", padx=4, pady=4)
        in_frame.pack(side="top", fill="both", expand=True, padx=8, pady=(4, 4))
        self.in_text = self._make_text(in_frame, mono)

        # Output pane
        out_frame = tk.LabelFrame(body, text="OUTPUT", padx=4, pady=4)
        out_frame.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))
        self.out_text = self._make_text(out_frame, mono)
        self.out_text.tag_configure("body", foreground="#1a6e1a")

        hint = tk.Label(
            self, anchor="w", padx=10, pady=4, fg="#666",
            text="←/→ turn    ↑/↓ conversation    Home/End first/last turn    q quit")
        hint.pack(side="bottom", fill="x")

        for seq in ("<Left>", "<Right>", "<Up>", "<Down>", "<Home>", "<End>"):
            self.bind(seq, self.on_key)
        self.bind("q", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())

        self.render()

    @staticmethod
    def _make_text(parent: tk.Widget, font) -> tk.Text:
        wrap = tk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        scroll = tk.Scrollbar(wrap)
        scroll.pack(side="right", fill="y")
        text = tk.Text(wrap, wrap="word", font=font, padx=8, pady=6,
                       yscrollcommand=scroll.set, height=10,
                       background="#fbfbfb", relief="flat")
        text.pack(side="left", fill="both", expand=True)
        scroll.config(command=text.yview)
        return text

    def on_key(self, event: tk.Event) -> None:
        convo = self.convos[self.ci]
        if event.keysym == "Left":
            self.ti = max(0, self.ti - 1)
        elif event.keysym == "Right":
            self.ti = min(len(convo) - 1, self.ti + 1)
        elif event.keysym == "Home":
            self.ti = 0
        elif event.keysym == "End":
            self.ti = len(convo) - 1
        elif event.keysym == "Up":
            self.ci = max(0, self.ci - 1)
            self.ti = 0
        elif event.keysym == "Down":
            self.ci = min(len(self.convos) - 1, self.ci + 1)
            self.ti = 0
        self.render()

    def render(self) -> None:
        convo = self.convos[self.ci]
        entry = convo[self.ti]
        m = entry.get("metadata") or {}

        self.header.config(text=(
            f"Conversation {self.ci + 1}/{len(self.convos)}     "
            f"Turn {self.ti + 1}/{len(convo)}\n"
            f"{m.get('task_id', '?')}   @ {m.get('scene', '?')}   "
            f"intent={m.get('intent', '?')}   cursor={m.get('cursor', '?')}"
        ))

        for widget, content, tag in (
            (self.in_text, entry.get("input", ""), None),
            (self.out_text, entry.get("output", ""), "body"),
        ):
            widget.config(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", content, tag) if tag else widget.insert("1.0", content)
            widget.config(state="disabled")
            widget.yview_moveto(0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", type=Path,
                    help="dataset json (default: newest in datasets/)")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed for the random conversation order (default: nondeterministic)")
    args = ap.parse_args()

    path = args.path or newest_dataset()
    if not path.exists():
        sys.exit(f"No such file: {path}")

    dataset = json.loads(path.read_text(encoding="utf-8"))
    if not dataset:
        sys.exit("Dataset is empty.")

    convos = group_conversations(dataset)
    random.Random(args.seed).shuffle(convos)
    print(f"{len(dataset)} turns across {len(convos)} conversations "
          f"(shuffled order) — {path.name}")
    Viewer(convos, path).mainloop()


if __name__ == "__main__":
    main()
