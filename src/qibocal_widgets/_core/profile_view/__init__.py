"""The title line of an execution: its timing, and its profile, folded.

Shown in place of a plain title, in both frontends: the toggle unfolds the
steps of the execution (see ``Completed.profile``), with buttons copying them
as Markdown or CSV, with their context, to report them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anywidget
import traitlets

__all__ = ["ProfileView"]

HERE = Path(__file__).parent


class ProfileView(anywidget.AnyWidget):
    """The title, the timing, and the profile of an execution."""

    _esm = HERE / "profile.js"
    _css = HERE / "profile.css"

    title = traitlets.Unicode().tag(sync=True)
    times = traitlets.Unicode("").tag(sync=True)
    steps = traitlets.List().tag(sync=True)
    """Steps, as ``{"step", "took", "at"}``: empty without a profile."""
    markdown = traitlets.Unicode("").tag(sync=True)
    csv = traitlets.Unicode("").tag(sync=True)
    unfolded = traitlets.Bool(False).tag(sync=True)
    """Whether the profile is shown (kept across renderings)."""

    def __init__(self, completed: Any, title: str, times: str):
        trace = getattr(completed, "trace", None)
        state = getattr(trace, "_view_state", None)
        steps, markdown, csv = [], "", ""
        if trace is not None:
            profile = completed.profile()
            steps = [
                {"step": row.step, "took": row._2, "at": row._3}
                for row in profile.itertuples()
            ]
            markdown = completed.profile_report()
            csv = completed.profile_report("csv")
        super().__init__(
            title=title,
            times=times,
            steps=steps,
            markdown=markdown,
            csv=csv,
            unfolded=bool(state and state.get("profile")),
        )
        if state is not None:
            self.observe(
                lambda change: state.update(profile=change["new"]),
                names=["unfolded"],
            )
