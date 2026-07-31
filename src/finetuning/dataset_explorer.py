"""GUI explorer for the finetuning dataset.

Browse the input/output pairs in ``datasets/dataset.json`` one conversation at
a time.

Keys
----
Right   next conversation (random, or forward through history after going back)
Left    previous conversation (walks back through visited history)
Down    next invocation in the current conversation
Up      previous invocation in the current conversation
Escape  quit

Run with::

    python -m finetuning.dataset_explorer [path/to/dataset.json]
"""

from __future__ import annotations

import json
import random
import sys
import threading
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import font as tkfont
from typing import Any

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "dataset.json"

BG = "#1e1f26"
PANEL = "#262832"
FG = "#d7dae0"
MUTED = "#8b90a0"
ACCENT = "#7aa2f7"
KEY = "#c3a6ff"
VALUE = "#9ece6a"

Invocation = dict[str, Any]


def load_conversations(path: Path) -> list[list[Invocation]]:
    """Group the flat dataset into conversations ordered by invocation index."""
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    grouped: dict[Any, list[Invocation]] = defaultdict(list)
    for entry in raw.values():
        grouped[entry["metadata"]["conversation_id"]].append(entry)

    conversations = []
    for conversation_id in sorted(grouped, key=lambda cid: (isinstance(cid, str), cid)):
        invocations = grouped[conversation_id]
        invocations.sort(key=lambda e: e["metadata"]["index_in_conversation"])
        conversations.append(invocations)
    return conversations


class DatasetExplorer:
    def __init__(self, root: tk.Tk, path: Path) -> None:
        self.root = root
        self.path = path
        self.conversations: list[list[Invocation]] = []

        # Visited conversation indices; ``cursor`` points into this list so that
        # Left/Right walk the same path backwards and forwards.
        self.history: list[int] = []
        self.cursor = -1
        self.unseen: list[int] = []
        self.invocation_index = 0

        root.title("Dataset Explorer")
        root.geometry("1500x900")
        root.configure(bg=BG)

        self.mono = tkfont.Font(family="Consolas", size=11)
        self.mono_bold = tkfont.Font(family="Consolas", size=11, weight="bold")
        self.ui = tkfont.Font(family="Segoe UI", size=10)
        self.ui_bold = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        self._build_widgets()
        self._bind_keys()

        self.status.set(f"Loading {path.name} ...")
        threading.Thread(target=self._load_async, daemon=True).start()

    # ------------------------------------------------------------------ build

    def _build_widgets(self) -> None:
        header = tk.Frame(self.root, bg=PANEL)
        header.pack(side="top", fill="x")

        self.status = tk.StringVar()
        tk.Label(
            header,
            textvariable=self.status,
            bg=PANEL,
            fg=ACCENT,
            font=self.ui_bold,
            anchor="w",
            padx=12,
            pady=8,
        ).pack(side="left")

        self.position = tk.StringVar()
        tk.Label(
            header,
            textvariable=self.position,
            bg=PANEL,
            fg=MUTED,
            font=self.ui,
            anchor="e",
            padx=12,
        ).pack(side="right")

        meta_frame = tk.Frame(self.root, bg=BG, padx=10, pady=6)
        meta_frame.pack(side="top", fill="x")
        meta_container, self.meta = self._make_text(meta_frame, height=7, wrap="word")
        meta_container.pack(fill="x")
        self.meta.tag_configure("key", foreground=KEY, font=self.mono_bold)
        self.meta.tag_configure("value", foreground=VALUE)

        panes = tk.PanedWindow(
            self.root,
            orient="horizontal",
            bg=BG,
            sashwidth=6,
            sashrelief="flat",
            borderwidth=0,
        )
        panes.pack(side="top", fill="both", expand=True, padx=10, pady=(4, 6))

        self.input_text = self._make_pane(panes, "INPUT")
        self.output_text = self._make_pane(panes, "OUTPUT")

        footer = tk.Label(
            self.root,
            text="  ← / →  conversation (forward = random)"
            "      ↑ / ↓  invocation in conversation"
            "      Esc  quit",
            bg=PANEL,
            fg=MUTED,
            font=self.ui,
            anchor="w",
            pady=6,
        )
        footer.pack(side="bottom", fill="x")

    def _make_pane(self, parent: tk.PanedWindow, title: str) -> tk.Text:
        frame = tk.Frame(parent, bg=BG)
        tk.Label(
            frame,
            text=title,
            bg=BG,
            fg=ACCENT,
            font=self.ui_bold,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        container, text = self._make_text(frame, wrap="none")
        container.pack(fill="both", expand=True)
        parent.add(frame, stretch="always", minsize=200)
        return text

    def _make_text(
        self, parent: tk.Widget, height: int | None = None, wrap: str = "none"
    ) -> tuple[tk.Frame, tk.Text]:
        """Build a read-only text pane; the caller packs the returned container."""
        container = tk.Frame(parent, bg=PANEL)
        text = tk.Text(
            container,
            bg=PANEL,
            fg=FG,
            font=self.mono,
            wrap=wrap,
            relief="flat",
            padx=10,
            pady=8,
            insertwidth=0,
            takefocus=0,
            height=height or 10,
            selectbackground="#3d59a1",
        )
        yscroll = tk.Scrollbar(container, command=text.yview, width=12)
        text.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.configure(state="disabled")
        text.bind("<MouseWheel>", lambda e, w=text: w.yview_scroll(-e.delta // 120, "units"))
        return container, text

    def _bind_keys(self) -> None:
        self.root.bind("<Right>", lambda _e: self.next_conversation())
        self.root.bind("<Left>", lambda _e: self.previous_conversation())
        self.root.bind("<Down>", lambda _e: self.step_invocation(1))
        self.root.bind("<Up>", lambda _e: self.step_invocation(-1))
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.focus_set()

    # ------------------------------------------------------------------- data

    def _load_async(self) -> None:
        try:
            conversations = load_conversations(self.path)
        except Exception as exc:  # surfaced in the UI rather than the console
            self.root.after(0, lambda: self.status.set(f"Failed to load: {exc}"))
            return
        self.root.after(0, lambda: self._on_loaded(conversations))

    def _on_loaded(self, conversations: list[list[Invocation]]) -> None:
        self.conversations = conversations
        if not conversations:
            self.status.set("Dataset is empty")
            return
        self.unseen = list(range(len(conversations)))
        random.shuffle(self.unseen)
        self.next_conversation()

    # -------------------------------------------------------------- navigation

    def next_conversation(self) -> None:
        if not self.conversations:
            return
        if self.cursor < len(self.history) - 1:
            # We had stepped back; go forward along the path already walked.
            self.cursor += 1
        else:
            if not self.unseen:
                # Every conversation has been shown once; reshuffle for another pass.
                self.unseen = list(range(len(self.conversations)))
                random.shuffle(self.unseen)
            self.history.append(self.unseen.pop())
            self.cursor = len(self.history) - 1
        self.invocation_index = 0
        self.render()

    def previous_conversation(self) -> None:
        if self.cursor > 0:
            self.cursor -= 1
            self.invocation_index = 0
            self.render()

    def step_invocation(self, delta: int) -> None:
        if not self.conversations:
            return
        conversation = self.conversations[self.history[self.cursor]]
        new_index = self.invocation_index + delta
        if 0 <= new_index < len(conversation):
            self.invocation_index = new_index
            self.render()

    # ----------------------------------------------------------------- render

    def render(self) -> None:
        conversation = self.conversations[self.history[self.cursor]]
        entry = conversation[self.invocation_index]
        metadata = entry["metadata"]

        self.status.set(
            f"Conversation {metadata['conversation_id']}"
            f"   ·   invocation {self.invocation_index + 1} / {len(conversation)}"
        )
        self.position.set(
            f"history {self.cursor + 1} / {len(self.history)}"
            f"   ·   {len(self.conversations)} conversations"
            f"   ·   {len(self.unseen)} unseen"
        )

        self._set_metadata(metadata)
        self._set_text(self.input_text, entry["input"])
        self._set_text(self.output_text, entry["output"])

    def _set_metadata(self, metadata: dict[str, Any]) -> None:
        self.meta.configure(state="normal")
        self.meta.delete("1.0", "end")
        width = max(len(k) for k in metadata) + 2
        for key, value in metadata.items():
            self.meta.insert("end", f"{key + ':':<{width}}", "key")
            self.meta.insert("end", f"{value}\n", "value")
        self.meta.configure(state="disabled")

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")
        widget.yview_moveto(0)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    if not path.exists():
        raise SystemExit(f"Dataset not found: {path}")

    root = tk.Tk()
    DatasetExplorer(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
