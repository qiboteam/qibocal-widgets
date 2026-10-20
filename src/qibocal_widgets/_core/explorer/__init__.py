"""Interactive explorer of platform states, for Jupyter and Marimo.

A single `anywidget <https://anywidget.dev>`_ serves both frontends. The logic
(path resolution, search, formatting, comparison, edits) lives in Python; the
browser side only renders the rows computed here, and sends back navigation,
edit, and option requests.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import anywidget
import traitlets

from ..state import (
    ROOTS,
    SEPARATOR,
    PlatformState,
    ReadOnlyState,
    _children,
    _get,
    is_leaf,
    normalize,
)

__all__ = ["Explorer", "format_value"]

HERE = Path(__file__).parent


def format_number(value: float) -> str:
    """Human-friendly number, as in the qibocal-report dashboard."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}"
    if not math.isfinite(value):
        return str(value)
    size = abs(value)
    if size >= 1e9:
        return f"{value / 1e9:.4f}".rstrip("0").rstrip(".") + " GHz"
    if size >= 1e6:
        return f"{value / 1e6:.4f}".rstrip("0").rstrip(".") + " MHz"
    if 1e3 <= size < 1e5:
        return f"{value / 1e3:.3f}".rstrip("0").rstrip(".") + " kHz"
    if 0 < size < 1e-4:
        return f"{value:.3e}"
    return f"{round(value, 6):g}"


def format_value(value: Any) -> str:
    """Display text of a leaf."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return format_number(value)
    if isinstance(value, list):
        return "[" + ", ".join(format_value(item) for item in value) + "]"
    return str(value)


class Explorer(anywidget.AnyWidget):
    """Explorer of a :class:`~qibocal_widgets.PlatformState`.

    Use :meth:`PlatformState.explore <qibocal_widgets.PlatformState.explore>`
    to create one. The navigation bar accepts paths, in any form accepted by
    :meth:`PlatformState.resolve <qibocal_widgets.PlatformState.resolve>`
    (full, within a document, or quoted in pasted code), and searches leaves
    by path otherwise.
    """

    _esm = HERE / "explorer.js"
    _css = HERE / "explorer.css"

    name = traitlets.Unicode().tag(sync=True)
    """How the state is referred to in code snippets."""
    path = traitlets.Unicode("").tag(sync=True)
    """Current canonical path (empty at the root)."""
    query = traitlets.Unicode("").tag(sync=True)
    """Current search, when the navigation text is not a path."""
    crumbs = traitlets.List().tag(sync=True)
    """Breadcrumbs: ``{label, path}`` from the root to the current path."""
    rows = traitlets.List().tag(sync=True)
    """Displayed entries: ``{key, path, kind, display, raw, changed, before}``."""
    editable = traitlets.Bool(False).tag(sync=True)
    """Whether leaves can be edited."""
    comparing = traitlets.Bool(False).tag(sync=True)
    """Whether a comparison state is set."""
    changed_only = traitlets.Bool(False).tag(sync=True)
    """Show only entries differing from the comparison state."""
    error = traitlets.Unicode("").tag(sync=True)
    """Last error, if any."""
    snippet = traitlets.Unicode("").tag(sync=True)
    """Code reproducing the last edit."""

    def __init__(
        self,
        state: PlatformState,
        path: str = "",
        *,
        editable: bool = False,
        compare: PlatformState | None = None,
    ):
        super().__init__(
            name=state.name,
            editable=editable and not state.readonly,
            comparing=compare is not None,
        )
        self.state = state
        """The explored state."""
        self.compare = compare
        """The state differences are highlighted against, if any."""
        self.on_msg(self._message)
        self.observe(lambda _: self.refresh(), names=["changed_only"])
        self.navigate(path)

    # -- requests -------------------------------------------------------------

    def navigate(self, text: str) -> None:
        """Go to the path designated by some text, or search for it."""
        documents = self.state.documents()
        resolved = normalize(text, documents)
        if resolved is not None:
            if resolved and is_leaf(_get(documents, resolved)):
                # show leaves within their parent, where they can be copied
                resolved = resolved.rpartition(SEPARATOR)[0]
            self.path, self.query = resolved, ""
        else:
            self.query = text.strip()
        self.error = ""
        self.refresh()

    def edit(self, path: str, text: str) -> None:
        """Set a leaf from the JSON text of its new value."""
        if not self.editable:
            self.error = "Editing is disabled"
            return
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            self.error = f"Not valid JSON: {text!r} (quote strings)"
            return
        try:
            self.state.update({path: value})
        except (KeyError, ValueError, ReadOnlyState) as error:
            self.error = f"{type(error).__name__}: {error}"
            return
        self.error = ""
        self.snippet = f"{self.name}.update({{{json.dumps(path)}: {value!r}}})"
        self.refresh()

    def _message(self, widget, content: dict, buffers) -> None:
        kind = content.get("kind")
        if kind == "navigate":
            self.navigate(content.get("text", ""))
        elif kind == "edit":
            self.edit(content["path"], content["value"])
        elif kind == "refresh":
            self.refresh()

    # -- rendering ------------------------------------------------------------

    def refresh(self) -> None:
        """Recompute the displayed entries from the current state."""
        documents = self.state.documents()
        changed = self._changed(documents)
        if self.query:
            rows = [
                self._leaf(path, path, value, changed)
                for path, value in self.state.find(self.query).items()
            ]
        else:
            if self.path and normalize(self.path, documents) is None:
                self.path = ""  # vanished (e.g. state replaced)
            node = _get(documents, self.path)
            rows = []
            for key, child in (
                _children(node)
                if self.path
                else ((root, documents[root]) for root in ROOTS if root in documents)
            ):
                path = f"{self.path}{SEPARATOR}{key}" if self.path else key
                if is_leaf(child):
                    rows.append(self._leaf(key, path, child, changed))
                else:
                    rows.append(self._branch(key, path, child, changed))
        if self.changed_only:
            rows = [row for row in rows if row["changed"]]
        self.rows = rows
        self.crumbs = self._crumbs()

    def _changed(self, documents: dict) -> dict[str, Any]:
        """Changed leaves, with their values in the comparison state."""
        if self.compare is None:
            return {}
        return {
            path: before for path, (before, _) in self.state.diff(self.compare).items()
        }

    def _leaf(self, key: str, path: str, value: Any, changed: dict) -> dict:
        return {
            "key": key,
            "path": path,
            "kind": "leaf",
            "display": format_value(value),
            "raw": json.dumps(value),
            "changed": path in changed,
            "before": format_value(changed[path]) if path in changed else "",
        }

    def _branch(self, key: str, path: str, value: Any, changed: dict) -> dict:
        prefix = path + SEPARATOR
        count = sum(1 for leaf in changed if leaf.startswith(prefix))
        size = sum(1 for _ in _children(value))
        return {
            "key": key,
            "path": path,
            "kind": "branch",
            "display": f"{size} entries" + (f", {count} changed" if count else ""),
            "raw": "",
            "changed": count > 0,
            "before": "",
        }

    def _crumbs(self) -> list[dict]:
        crumbs = [{"label": self.name, "path": ""}]
        if self.path:
            segments = self.path.split(SEPARATOR)
            for index, segment in enumerate(segments):
                crumbs.append(
                    {"label": segment, "path": SEPARATOR.join(segments[: index + 1])}
                )
        return crumbs
