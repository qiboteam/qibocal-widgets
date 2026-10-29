"""A button for Jupyter and Marimo, confirming or repeating executions.

An anywidget, so that clicks reach Python in both frontends, also when it is
displayed inside other outputs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..pending import Pending
    from ..updates import Updates

__all__ = ["Button", "again_button", "run_button", "update_button"]

ALL = object()
"""All the targets of an update."""

HERE = Path(__file__).parent


class Button(anywidget.AnyWidget):
    """A button calling ``on_click()``, disabled once clicked."""

    _esm = HERE / "button.js"
    _css = HERE / "button.css"

    label = traitlets.Unicode().tag(sync=True)
    tooltip = traitlets.Unicode("").tag(sync=True)
    disabled = traitlets.Bool(False).tag(sync=True)

    def __init__(self, label: str, on_click: Callable[[], None], tooltip: str = ""):
        super().__init__(label=label, tooltip=tooltip)
        self._on_click = on_click
        self.on_msg(self._message)

    def click(self) -> None:
        """Click the button, as from the frontend."""
        if self.disabled:
            return
        self.disabled = True
        self._on_click()

    def _message(self, widget, content: dict, buffers) -> None:
        if content.get("event") == "click":
            self.click()


def tooltip(pending: Pending) -> str:
    """What the execution of a pending execution overrides, for display."""
    overrides = ", ".join(
        f"{key}={value!r}" for key, value in pending.overrides.items()
    )
    return f"{pending.name}({overrides})" if overrides else pending.name


def run_button(pending: Pending) -> Button:
    """The *Run* button of an execution waiting for confirmation."""
    return Button(f"▶ Run {pending.name}", pending.start, tooltip(pending))


def again_button(pending: Pending) -> Button:
    """The *Run again* button of a completed execution."""
    return Button("↻ Run again", pending.rerun, tooltip(pending))


def update_button(updates: Updates, target: Any = ALL) -> Button:
    """A button applying the platform update, to all targets or to one.

    It shows when applied (also by other buttons, from code, or automatically),
    and offers to retry on failure.
    """
    whole = target is ALL
    if whole and updates.per_target:
        labels = ("⤓ Update all targets", "✓ All applied")
        tooltip_ = "Apply the fitted values of all targets to the platform"
    else:
        labels = ("⤓ Update", "✓ Applied")
        tooltip_ = "Apply the fitted values to the platform"

    def applied() -> bool:
        return not updates.pending if whole else updates.is_applied(target)

    def show(_: Any = None) -> None:
        done = applied()
        button.label = labels[done]
        button.disabled = done

    def click() -> None:
        button.label = "Updating…"
        try:
            updates.apply(None if whole else [target])
        except Exception as error:  # noqa: BLE001 - shown, to retry
            button.label = "⚠ Update failed: retry"
            button.tooltip = f"{type(error).__name__}: {error}"
            button.disabled = False
        else:
            show()

    button = Button(labels[0], click, tooltip_)
    show()
    updates.on_change(show)
    return button
