"""GUI explorer for the finetuning dataset.

Browse the input/output pairs of the newest ``dataset_*.json`` one conversation
at a time, or switch to one of the flat views that ignore conversation
boundaries.

The generator appends *tool-failure* pairs after the real rows (metadata
``error_injected: true``). Those rows reuse their source row's
``conversation_id`` / ``index_in_conversation``, so folding them into the
conversations they were derived from duplicates indices and makes ~4 out of 5
conversations look like they contain failures. They are kept out of the
conversation and token views and get their own view instead (``E``), with
``G`` jumping between an error pair and the row it was built from.

Keys
----
Right   next conversation / next pair in a flat view
Left    previous conversation / previous pair in a flat view
Down    next invocation in the current conversation / next pair
Up      previous invocation in the current conversation / previous pair
T       toggle token view (clean pairs, largest first)
E       toggle error view (only the injected tool-failure pairs)
G       error pair -> its source row, and back to the errors made from a row
S       show the scene this row was generated against
H       show a size histogram across the whole dataset
Escape  quit (or close the popup window)

Run with::

    python src/dataset_generation/dataset_explorer.py [path/to/dataset.json]

The argument may also be a directory, in which case its newest
``dataset_*.json`` is opened; with no argument the newest dataset from the
generator's output directory or the training ``datasets/`` directory wins.
"""

from __future__ import annotations

import json
import random
import sys
import threading
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import font as tkfont
from typing import Any

_HERE = Path(__file__).resolve().parent

# Where datasets show up: the generator writes next to itself, training copies
# live in the finetuning package. Newest across both wins.
DATASET_DIRS = [_HERE, _HERE.parent / "finetuning" / "datasets"]

BG = "#1e1f26"
PANEL = "#262832"
FG = "#d7dae0"
MUTED = "#8b90a0"
ACCENT = "#7aa2f7"
KEY = "#c3a6ff"
VALUE = "#9ece6a"
ERR = "#f7768e"

# Metadata rendered as a single flowing chip line, in this order.
COMPACT_FIELDS = [
    ("id", "id"),
    ("scene_id", "scene"),
    ("conversation_id", "conv"),
    ("index_in_conversation", "step"),
    ("task_id", "task"),
    ("answer_label", "label"),
    ("answer_macro", "macro"),
    ("answer_macro_id", "macro_id"),
    ("error_injected", "error_injected"),
    ("source_id", "from row"),
]
LONG_FIELDS = ["prompt", "answer"]

BLOCK_HEADERS = ("PROGRAM", "MEMORY", "RESOLUTION", "TOOL CALL", "TOOL RESULTS",
                 "ANSWER")

Invocation = dict[str, Any]


def _as_int(value: Any) -> tuple[int, Any]:
    """Sort key that keeps numeric ids numeric and pushes anything else last."""
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def newest_dataset(directories: list[Path]) -> Path | None:
    """Newest ``dataset_*.json`` across ``directories``, reports excluded."""
    candidates = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.glob("dataset*.json"):
            if path.stem.endswith("_report") or "_seen_" in path.stem:
                continue
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_report(dataset_path: Path) -> dict[str, Any] | None:
    """The generator's ``*_report.json``, which may have stayed behind in the
    generator directory when the dataset itself was moved to ``datasets/``."""
    name = f"{dataset_path.stem}_report.json"
    for candidate in (dataset_path.with_name(name), _HERE / name):
        if candidate.is_file():
            try:
                with open(candidate, encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, ValueError):
                return None
    return None


def find_scenes_dir(dataset_path: Path, report: dict[str, Any] | None) -> Path | None:
    """Directory holding one ``scene_XXXX.json`` per ``scene_id``."""
    candidates = []
    if report and report.get("scenes_dir"):
        candidates.append(Path(report["scenes_dir"]))
    stem = dataset_path.stem
    candidates += [
        dataset_path.parent / "scenes" / stem,
        _HERE / "gen" / "scenes" / stem,
        _HERE / "scenes" / stem,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


@dataclass
class Dataset:
    """The dataset split the way it is browsed: clean conversations on one side,
    injected tool-failure pairs on the other."""

    path: Path
    rows: list[Invocation] = field(default_factory=list)
    conversations: list[list[Invocation]] = field(default_factory=list)
    errors: list[Invocation] = field(default_factory=list)
    size_unit: str = "chars"
    # row id -> (conversation index, invocation index) for the clean rows
    location: dict[Any, tuple[int, int]] = field(default_factory=dict)
    # source row id -> indices into ``errors``
    errors_by_source: dict[Any, list[int]] = field(default_factory=lambda: defaultdict(list))
    report: dict[str, Any] | None = None
    scenes_dir: Path | None = None


def load_dataset(path: Path) -> Dataset:
    """Read the dataset and split it into conversations and injected errors.

    Old datasets carry neither ``id`` nor ``error_injected``; those simply come
    out as one big clean set with row ids falling back to the JSON key.

    Each entry gets two private top-level keys, ``_id`` and ``_size``, so the
    metadata dict stays exactly what the generator wrote.
    """
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    report = find_report(path)
    dataset = Dataset(path=path, report=report,
                      scenes_dir=find_scenes_dir(path, report))

    ordered = sorted(raw.items(), key=lambda kv: _as_int(kv[0]))
    # The current generator no longer counts tokens, so fall back to sizing rows
    # by character count -- same ordering intent, honestly labelled.
    tokenised = any(
        "llama_tokens" in entry.get("metadata", {}) for _, entry in ordered[:50]
    )
    dataset.size_unit = "llama_tokens" if tokenised else "chars"

    grouped: dict[Any, list[Invocation]] = defaultdict(list)
    for key, entry in ordered:
        metadata = entry.setdefault("metadata", {})
        entry["_id"] = metadata.get("id", _as_int(key)[1])
        entry["_size"] = (
            metadata.get("llama_tokens", 0) if tokenised
            else len(entry.get("input", "")) + len(entry.get("output", ""))
        )
        dataset.rows.append(entry)
        if metadata.get("error_injected"):
            dataset.errors_by_source[metadata.get("source_id")].append(len(dataset.errors))
            dataset.errors.append(entry)
        else:
            grouped[metadata.get("conversation_id")].append(entry)

    for conversation_id in sorted(grouped, key=_as_int):
        invocations = grouped[conversation_id]
        invocations.sort(key=lambda e: _as_int(e["metadata"].get("index_in_conversation")))
        index = len(dataset.conversations)
        for position, entry in enumerate(invocations):
            dataset.location[entry["_id"]] = (index, position)
        dataset.conversations.append(invocations)
    return dataset


class DatasetExplorer:
    def __init__(self, root: tk.Tk, path: Path) -> None:
        self.root = root
        self.path = path
        self.ds = Dataset(path=path)

        # Visited conversation indices; ``cursor`` points into this list so that
        # Left/Right walk the same path backwards and forwards.
        self.history: list[int] = []
        self.cursor = -1
        self.unseen: list[int] = []
        self.invocation_index = 0

        # "conversation" walks conversations; "token" walks every clean
        # invocation sorted by size descending; "error" walks the injected
        # tool-failure pairs in generation order.
        self.mode = "conversation"
        self.flat: list[Invocation] = []
        self.flat_index = 0
        self.error_index = 0
        self._hist_window: tk.Toplevel | None = None
        self._scene_window: tk.Toplevel | None = None
        self._scene_cache: dict[str, Any] = {}

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
        self.status_label = tk.Label(
            header,
            textvariable=self.status,
            bg=PANEL,
            fg=ACCENT,
            font=self.ui_bold,
            anchor="w",
            padx=12,
            pady=8,
        )
        self.status_label.pack(side="left")

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

        self.token_button_text = tk.StringVar(value="Token view  (T)")
        self.error_button_text = tk.StringVar(value="Errors  (E)")
        self._make_button(
            header, textvariable=self.token_button_text, command=self.toggle_token_mode
        ).pack(side="right", padx=(0, 6), pady=6)
        self._make_button(
            header, textvariable=self.error_button_text, command=self.toggle_error_mode
        ).pack(side="right", padx=(0, 6), pady=6)
        self._make_button(
            header, text="Scene  (S)", command=self.show_scene
        ).pack(side="right", padx=(0, 6), pady=6)
        self._make_button(
            header, text="Histogram  (H)", command=self.show_histogram
        ).pack(side="right", padx=(0, 6), pady=6)

        meta_frame = tk.Frame(self.root, bg=BG, padx=10, pady=6)
        meta_frame.pack(side="top", fill="x")
        meta_container, self.meta = self._make_text(meta_frame, height=7, wrap="word")
        meta_container.pack(fill="x")
        self.meta.tag_configure("key", foreground=KEY, font=self.mono_bold)
        self.meta.tag_configure("value", foreground=VALUE)
        self.meta.tag_configure("muted", foreground=MUTED)
        self.meta.tag_configure("error", foreground=ERR, font=self.mono_bold)

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

        self.footer_text = tk.StringVar()
        footer = tk.Label(
            self.root,
            textvariable=self.footer_text,
            bg=PANEL,
            fg=MUTED,
            font=self.ui,
            anchor="w",
            pady=6,
        )
        footer.pack(side="bottom", fill="x")
        self._update_footer()

    def _update_footer(self) -> None:
        tail = "      S  scene      H  histogram      Esc  quit"
        if self.mode == "token":
            self.footer_text.set(
                f"  ← ↑ / → ↓  prev / next pair ({self.ds.size_unit} descending)"
                "      T  back to conversations      E  errors" + tail
            )
        elif self.mode == "error":
            self.footer_text.set(
                "  ← ↑ / → ↓  prev / next tool-failure pair"
                "      G  go to the row it was made from"
                "      E  back to conversations" + tail
            )
        else:
            self.footer_text.set(
                "  ← / →  conversation (forward = random)"
                "      ↑ / ↓  invocation      G  errors made from this row"
                "      T  token view      E  errors" + tail
            )

    def _make_button(self, parent: tk.Widget, **kwargs: Any) -> tk.Button:
        return tk.Button(
            parent,
            bg=BG,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=BG,
            font=self.ui,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=4,
            takefocus=0,
            cursor="hand2",
            **kwargs,
        )

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
        text.tag_configure("block", foreground=ACCENT, font=self.mono_bold)
        text.tag_configure("user", foreground=KEY, font=self.mono_bold)
        text.tag_configure("failed", foreground=ERR, font=self.mono_bold)
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
        self.root.bind("<Right>", lambda _e: self._forward())
        self.root.bind("<Left>", lambda _e: self._backward())
        self.root.bind("<Down>", lambda _e: self._step_down())
        self.root.bind("<Up>", lambda _e: self._step_up())
        for key, command in (
            ("t", self.toggle_token_mode),
            ("e", self.toggle_error_mode),
            ("g", self.goto_linked),
            ("s", self.show_scene),
            ("h", self.show_histogram),
        ):
            self.root.bind(f"<{key}>", lambda _e, c=command: c())
            self.root.bind(f"<{key.upper()}>", lambda _e, c=command: c())
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.focus_set()

    def _forward(self) -> None:
        if self.mode == "token":
            self.step_flat(1)
        elif self.mode == "error":
            self.step_error(1)
        else:
            self.next_conversation()

    def _backward(self) -> None:
        if self.mode == "token":
            self.step_flat(-1)
        elif self.mode == "error":
            self.step_error(-1)
        else:
            self.previous_conversation()

    def _step_down(self) -> None:
        if self.mode == "token":
            self.step_flat(1)
        elif self.mode == "error":
            self.step_error(1)
        else:
            self.step_invocation(1)

    def _step_up(self) -> None:
        if self.mode == "token":
            self.step_flat(-1)
        elif self.mode == "error":
            self.step_error(-1)
        else:
            self.step_invocation(-1)

    # ------------------------------------------------------------------- data

    def _load_async(self) -> None:
        try:
            dataset = load_dataset(self.path)
        except Exception as exc:  # surfaced in the UI rather than the console
            self.root.after(0, lambda: self.status.set(f"Failed to load: {exc}"))
            return
        self.root.after(0, lambda: self._on_loaded(dataset))

    def _on_loaded(self, dataset: Dataset) -> None:
        self.ds = dataset
        if not dataset.conversations and not dataset.errors:
            self.status.set("Dataset is empty")
            return
        self.flat = sorted(
            (inv for conv in dataset.conversations for inv in conv),
            key=lambda e: e["_size"],
            reverse=True,
        )
        self.flat_index = 0
        self.error_index = 0
        self.unseen = list(range(len(dataset.conversations)))
        random.shuffle(self.unseen)
        self.error_button_text.set(f"Errors: {len(dataset.errors)}  (E)")
        self._update_footer()
        if dataset.conversations:
            self.next_conversation()
        else:
            self.mode = "error"
            self.render()

    # -------------------------------------------------------------- navigation

    def next_conversation(self) -> None:
        if not self.ds.conversations:
            return
        if self.cursor < len(self.history) - 1:
            # We had stepped back; go forward along the path already walked.
            self.cursor += 1
        else:
            if not self.unseen:
                # Every conversation has been shown once; reshuffle for another pass.
                self.unseen = list(range(len(self.ds.conversations)))
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
        if not self.ds.conversations:
            return
        conversation = self.ds.conversations[self.history[self.cursor]]
        new_index = self.invocation_index + delta
        if 0 <= new_index < len(conversation):
            self.invocation_index = new_index
            self.render()

    def step_flat(self, delta: int) -> None:
        if not self.flat:
            return
        new_index = self.flat_index + delta
        if 0 <= new_index < len(self.flat):
            self.flat_index = new_index
            self.render()

    def step_error(self, delta: int) -> None:
        if not self.ds.errors:
            return
        new_index = self.error_index + delta
        if 0 <= new_index < len(self.ds.errors):
            self.error_index = new_index
            self.render()

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.token_button_text.set(
            "Conversations  (T)" if mode == "token" else "Token view  (T)"
        )
        self.error_button_text.set(
            "Conversations  (E)" if mode == "error"
            else f"Errors: {len(self.ds.errors)}  (E)"
        )
        self._update_footer()

    def toggle_token_mode(self) -> None:
        if not self.ds.conversations:
            return
        self._set_mode("conversation" if self.mode == "token" else "token")
        self.render()
        self.root.focus_set()

    def toggle_error_mode(self) -> None:
        if self.mode == "error":
            if not self.ds.conversations:
                return
            self._set_mode("conversation")
        else:
            if not self.ds.errors:
                self.status.set("This dataset has no injected tool-failure pairs")
                return
            self._set_mode("error")
        self.render()
        self.root.focus_set()

    def goto_linked(self) -> None:
        """Follow the link between an injected pair and its source row."""
        entry = self.current_entry()
        if entry is None:
            return
        metadata = entry["metadata"]
        if metadata.get("error_injected"):
            source_id = metadata.get("source_id")
            location = self.ds.location.get(source_id)
            if location is None:
                self.status.set(f"Source row {source_id} is not in any conversation")
                return
            conversation_index, invocation_index = location
            self._set_mode("conversation")
            self.history.append(conversation_index)
            self.cursor = len(self.history) - 1
            self.invocation_index = invocation_index
        else:
            derived = self.ds.errors_by_source.get(entry["_id"])
            if not derived:
                self.status.set("No tool-failure pair was made from this row")
                return
            self._set_mode("error")
            self.error_index = derived[0]
        self.render()
        self.root.focus_set()

    # ----------------------------------------------------------------- render

    def current_entry(self) -> Invocation | None:
        if self.mode == "token":
            return self.flat[self.flat_index] if self.flat else None
        if self.mode == "error":
            return self.ds.errors[self.error_index] if self.ds.errors else None
        if not self.ds.conversations or self.cursor < 0:
            return None
        return self.ds.conversations[self.history[self.cursor]][self.invocation_index]

    def render(self) -> None:
        if self.mode == "token":
            self._render_flat()
        elif self.mode == "error":
            self._render_error()
        else:
            self._render_conversation()

    def _render_conversation(self) -> None:
        conversation = self.ds.conversations[self.history[self.cursor]]
        entry = conversation[self.invocation_index]
        metadata = entry["metadata"]

        derived = len(self.ds.errors_by_source.get(entry["_id"], ()))
        self.status_label.configure(fg=ACCENT)
        self.status.set(
            f"Conversation {metadata.get('conversation_id')}"
            f"   ·   invocation {self.invocation_index + 1} / {len(conversation)}"
            + (f"   ·   {derived} tool-failure pair(s) from this row  (G)"
               if derived else "")
        )
        self.position.set(
            f"history {self.cursor + 1} / {len(self.history)}"
            f"   ·   {len(self.ds.conversations)} conversations"
            f"   ·   {len(self.unseen)} unseen"
        )
        self._show_entry(entry)

    def _render_flat(self) -> None:
        entry = self.flat[self.flat_index]
        metadata = entry["metadata"]

        self.status_label.configure(fg=ACCENT)
        self.status.set(
            f"Token view   ·   {entry['_size']} {self.ds.size_unit}"
            f"   ·   conversation {metadata.get('conversation_id')}"
        )
        self.position.set(
            f"pair {self.flat_index + 1} / {len(self.flat)}"
            f"   ·   sorted by {self.ds.size_unit} ↓   ·   errors excluded"
        )
        self._show_entry(entry)

    def _render_error(self) -> None:
        entry = self.ds.errors[self.error_index]
        metadata = entry["metadata"]

        self.status_label.configure(fg=ERR)
        self.status.set(
            f"⚠  Tool-failure pair   ·   built from row {metadata.get('source_id')}"
            f"   ·   conversation {metadata.get('conversation_id')}"
        )
        self.position.set(
            f"error {self.error_index + 1} / {len(self.ds.errors)}"
            f"   ·   {len(self.ds.errors) / max(1, len(self.ds.rows)):.0%} of the dataset"
        )
        self._show_entry(entry)

    def _show_entry(self, entry: Invocation) -> None:
        self._set_metadata(entry["metadata"])
        self._set_text(self.input_text, entry.get("input", ""))
        self._set_text(self.output_text, entry.get("output", ""))

    # ---------------------------------------------------------------- popups

    def _popup(self, title: str, geometry: str) -> tk.Toplevel:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(geometry)
        window.configure(bg=BG)
        window.bind("<Escape>", lambda _e: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        return window

    def show_scene(self) -> None:
        """Show the world the current row was generated against."""
        entry = self.current_entry()
        if entry is None:
            return
        scene_id = entry["metadata"].get("scene_id")
        if scene_id is None:
            self.status.set("This dataset predates scene ids")
            return
        if self.ds.scenes_dir is None:
            self.status.set(f"No scenes directory found for {self.path.stem}")
            return

        scene = self._scene_cache.get(scene_id)
        if scene is None:
            scene_path = self.ds.scenes_dir / f"{scene_id}.json"
            try:
                with open(scene_path, encoding="utf-8") as handle:
                    scene = json.load(handle)
            except (OSError, ValueError) as exc:
                self.status.set(f"Scene unavailable: {exc}")
                return
            self._scene_cache[scene_id] = scene

        if self._scene_window is not None and self._scene_window.winfo_exists():
            self._scene_window.destroy()
        window = self._popup(f"{scene_id}  ·  {self.ds.scenes_dir.name}", "1100x800")
        self._scene_window = window
        container, text = self._make_text(window, wrap="none")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        text.tag_configure("block", foreground=ACCENT, font=self.mono_bold)
        self._set_text(text, self._format_scene(scene_id, scene))

    def _format_scene(self, scene_id: str, scene: dict[str, Any]) -> str:
        positions = scene.get("positions", {})
        by_kind: dict[str, list[str]] = defaultdict(list)
        for name, config in positions.items():
            by_kind[config.get("type", "?")].append(name)

        lines = [
            f"SCENE {scene_id}",
            f"locations   {len(scene.get('object_locations', []))}: "
            + ", ".join(scene.get("object_locations", [])),
            f"types       {len(scene.get('object_types', []))}: "
            + ", ".join(scene.get("object_types", [])),
            f"robot_start {scene.get('robot_start')}",
            f"positions   {len(positions)} ("
            + ", ".join(f"{kind} {len(names)}" for kind, names in sorted(by_kind.items()))
            + ")",
            "",
        ]
        for kind in sorted(by_kind):
            lines.append(f"{kind}")
            for name in by_kind[kind]:
                config = positions[name]
                detail = " ".join(
                    f"{k}={v}" for k, v in config.items()
                    if k != "type" and v is not None
                )
                lines.append(f"  {name}    {detail}")
            lines.append("")
        lines.append("RAW")
        lines.append(json.dumps(scene, indent=1, ensure_ascii=False))
        return "\n".join(lines)

    def show_histogram(self) -> None:
        if not self.ds.rows:
            return
        if self._hist_window is not None and self._hist_window.winfo_exists():
            self._hist_window.deiconify()
            self._hist_window.lift()
            self._hist_window.focus_set()
            return
        try:
            import statistics

            from matplotlib.backends.backend_tkagg import (
                FigureCanvasTkAgg,
                NavigationToolbar2Tk,
            )
            from matplotlib.figure import Figure
        except Exception as exc:  # surface in the UI rather than crash the app
            self.status.set(f"Histogram unavailable: {exc}")
            return

        clean = [e["_size"] for e in self.ds.rows
                 if not e["metadata"].get("error_injected")]
        failures = [e["_size"] for e in self.ds.errors]
        sizes = clean + failures

        win = self._popup(f"{self.ds.size_unit} histogram", "960x640")
        self._hist_window = win

        fig = Figure(figsize=(9.6, 6.4), dpi=100, facecolor=BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(PANEL)
        if failures:
            ax.hist([clean, failures], bins=80, stacked=True,
                    color=[ACCENT, ERR], edgecolor=BG, linewidth=0.4,
                    label=[f"clean ({len(clean)})", f"tool-failure ({len(failures)})"])
        else:
            ax.hist(clean, bins=80, color=ACCENT, edgecolor=BG, linewidth=0.4,
                    label=f"clean ({len(clean)})")

        mean = statistics.fmean(sizes)
        median = statistics.median(sizes)
        ax.axvline(mean, color=VALUE, linestyle="--", linewidth=1.3, label=f"mean {mean:.0f}")
        ax.axvline(median, color=KEY, linestyle="--", linewidth=1.3, label=f"median {median:.0f}")

        ax.set_title(
            f"{self.ds.size_unit} across {len(sizes)} invocations"
            f"   (min {min(sizes)}, max {max(sizes)})",
            color=FG,
        )
        ax.set_xlabel(self.ds.size_unit, color=FG)
        ax.set_ylabel("invocations", color=FG)
        ax.tick_params(colors=MUTED)
        for spine in ax.spines.values():
            spine.set_color(MUTED)
        ax.legend(facecolor=PANEL, edgecolor=MUTED, labelcolor=FG)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, win, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    # ------------------------------------------------------------------ paint

    def _set_metadata(self, metadata: dict[str, Any]) -> None:
        """Identity fields flow across one chip line, prompt/answer get their own,
        and anything the generator adds later still shows up at the end."""
        self.meta.configure(state="normal")
        self.meta.delete("1.0", "end")

        shown = set()
        first = True
        for key, label in COMPACT_FIELDS:
            if key not in metadata:
                continue
            shown.add(key)
            value = metadata[key]
            if key == "error_injected" and not value:
                continue
            if not first:
                self.meta.insert("end", "   ·   ", "muted")
            first = False
            tag = "error" if key in ("error_injected", "source_id") else "value"
            self.meta.insert("end", f"{label} ", "key")
            self.meta.insert("end", "—" if value is None else str(value), tag)
        self.meta.insert("end", "\n")

        for key in LONG_FIELDS:
            if key in metadata:
                shown.add(key)
                self.meta.insert("end", f"{key}: ", "key")
                self.meta.insert("end", f"{metadata[key]}\n", "value")

        for key, value in metadata.items():
            if key not in shown:
                self.meta.insert("end", f"{key}: ", "key")
                self.meta.insert("end", f"{value}\n", "value")
        self.meta.configure(state="disabled")

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        for number, line in enumerate(content.split("\n"), start=1):
            if line in BLOCK_HEADERS:
                widget.tag_add("block", f"{number}.0", f"{number}.end")
            elif line.startswith("User:"):
                widget.tag_add("user", f"{number}.0", f"{number}.5")
            column = line.find('status: "ERROR"')
            if column >= 0:
                widget.tag_add("failed", f"{number}.{column}",
                               f"{number}.{column + 15}")
        widget.configure(state="disabled")
        widget.yview_moveto(0)


def resolve_path(argument: str | None) -> Path:
    if argument:
        path = Path(argument)
        if path.is_dir():
            found = newest_dataset([path])
            if found is None:
                raise SystemExit(f"No dataset_*.json in {path}")
            return found
        if not path.exists():
            raise SystemExit(f"Dataset not found: {path}")
        return path
    found = newest_dataset(DATASET_DIRS)
    if found is None:
        raise SystemExit(
            "No dataset_*.json found in "
            + " or ".join(str(d) for d in DATASET_DIRS)
        )
    return found


def main() -> None:
    path = resolve_path(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Opening {path}")

    root = tk.Tk()
    DatasetExplorer(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
