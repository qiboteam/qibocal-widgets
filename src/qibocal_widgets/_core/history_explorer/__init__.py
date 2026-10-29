"""Explorer of the platform history: two entries compared, and restored."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

from ..explorer import format_value

if TYPE_CHECKING:
    from ..history import PlatformHistory

__all__ = ["HistoryExplorer"]

HERE = Path(__file__).parent


class HistoryExplorer(anywidget.AnyWidget):
    """The entries of a history, the differences between two of them (A and
    B), and buttons restoring A, entirely or for the selected paths."""

    _esm = HERE / "history.js"
    _css = HERE / "history.css"

    name = traitlets.Unicode("executor.history").tag(sync=True)
    entries = traitlets.List().tag(sync=True)
    """Entries, newest first, with their position in the lineage of the head."""
    a = traitlets.Int(0).tag(sync=True)
    b = traitlets.Int(0).tag(sync=True)
    diff = traitlets.List().tag(sync=True)
    """Leaves differing between A and B."""
    error = traitlets.Unicode("").tag(sync=True)
    snippet = traitlets.Unicode("").tag(sync=True)
    """Code reproducing the last restore."""

    def __init__(
        self, history: PlatformHistory, a: int | None = None, b: int | None = None
    ):
        super().__init__()
        self.history = history
        self._selected = False
        self.on_msg(self._message)
        self.refresh(a, b)

    def refresh(self, a: int | None = None, b: int | None = None) -> None:
        """Recompute the entries and the differences, e.g. after new entries."""
        entries = self.history.entries
        if not entries:
            self.entries, self.diff = [], []
            self.error = "No platform change recorded yet"
            return
        head = self.history.head
        lineage = {entry.id for entry in self.history.lineage(head.id)}
        self.entries = [
            {
                "id": entry.id,
                "parent": entry.parent,
                "time": f"{entry.at:%H:%M:%S}",
                "change": entry.describe(),
                "leaves": len(entry.changes),
                "head": entry.id == head.id,
                "lineage": entry.id in lineage,
            }
            for entry in reversed(entries)
        ]
        if not self._selected:
            # at first, the latest change: the head against its parent
            a = (head.parent or 0) if a is None else a
            b = head.id if b is None else b
            self._selected = True
        self.a = self.history[self.a if a is None else a].id
        self.b = self.history[self.b if b is None else b].id
        self.error = ""
        self._compare()

    def select(self, a: int, b: int) -> None:
        """Compare two entries."""
        self.a, self.b = self.history[a].id, self.history[b].id
        self.error = ""
        self._compare()

    def restore(self, paths: list[str] | None = None) -> None:
        """Restore entry A, entirely or for some paths."""
        try:
            self.history.restore(self.a, paths)
        except (KeyError, ValueError) as error:
            self.error = f"{type(error).__name__}: {error}"
            return
        args = str(self.a) if paths is None else f"{self.a}, {json.dumps(paths)}"
        self.snippet = f"{self.name}.restore({args})"
        self.refresh(a=self.a, b=self.history.head.id)

    def _compare(self) -> None:
        self.diff = [
            {
                "path": path,
                "a": _display(a),
                "b": _display(b),
                "a_exact": json.dumps(a),
                "b_exact": json.dumps(b),
            }
            for path, (a, b) in self.history.diff(self.a, self.b).items()
        ]

    def _message(self, widget, content: dict, buffers) -> None:
        kind = content.get("kind")
        if kind == "select":
            self.select(int(content["a"]), int(content["b"]))
        elif kind == "restore":
            self.restore(content.get("paths"))
        elif kind == "refresh":
            self.refresh()


def _display(value: Any) -> str:
    return "—" if value is None else format_value(value)
