"""Jupyter rendering of executions and the Jupyter-flavored executor.

Rendering relies on ``ipywidgets`` (accordions and tabs) and on the native
Jupyter renderers of pandas and Plotly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import ipywidgets as widgets
from IPython.display import display as ipy_display
from qibocal.auto.task import Completed as QibocalCompleted

from . import layout
from .button import again_button, run_button, update_button
from .completed import MIMEBUNDLE, Completed
from .data import data_frames
from .frontend import Frontend
from .pending import DONE, FAILED, READY, Pending
from .profile_view import ProfileView
from .progress_view import ProgressView
from .reports import Report, reports, reports_of

if TYPE_CHECKING:
    from .updates import Updates

__all__ = [
    "Jupyter",
    "display",
    "show_data",
    "show_reports",
    "wrap",
]


def _output(*objects: Any) -> widgets.Output:
    """Capture the display of some objects into an output widget."""
    out = widgets.Output()
    with out:
        for obj in objects:
            ipy_display(obj)
    return out


def _accordion(
    items: dict[str, widgets.Widget], expanded: bool = False
) -> widgets.Accordion:
    """Accordion with the given titles, optionally with the first item open."""
    accordion = widgets.Accordion(children=list(items.values()))
    for index, title in enumerate(items):
        accordion.set_title(index, title)
    accordion.selected_index = 0 if expanded and items else None
    return accordion


def _message(text: str) -> widgets.HTML:
    return widgets.HTML(f"<em>{text}</em>")


def show_data(data: Any) -> widgets.Widget:
    """Accordion of raw data tables, one entry per target.

    Args:
        data: a Qibocal ``Data`` instance, or an execution (``Completed``), in
            which case its acquired data is used.
    """
    if isinstance(data, QibocalCompleted):
        data = data.data
    tables = {
        layout.data_title(target): _output(frame)
        for target, frame in data_frames(data).items()
    }
    if not tables:
        return _message("No acquired data to display.")
    return _accordion(tables, expanded=layout.expanded(tables))


def _fit_results(table: str) -> widgets.Accordion:
    """Fit results table, centered, folded in a nested accordion."""
    centered = widgets.Box(
        [widgets.HTML(table)],
        layout=widgets.Layout(justify_content="center", width="100%"),
    )
    return _accordion({layout.FIT_RESULTS: centered})


def _row(
    left: widgets.Widget | None,
    right: Sequence[widgets.Widget],
    align: str = "flex-start",
) -> widgets.HBox:
    """A line: ``left`` filling it, ``right`` aligned to the right.

    Aligned on top by default, so that ``right`` stays in place when ``left``
    unfolds (e.g. the fit results).
    """
    filler = left if left is not None else widgets.HTML("")
    filler.layout.flex = "1 1 auto"
    filler.layout.min_width = "0"
    buttons = widgets.HBox(list(right), layout=widgets.Layout(flex="0 0 auto"))
    return widgets.HBox(
        [filler, buttons],
        layout=widgets.Layout(width="100%", align_items=align, gap="0.5em"),
    )


def _report_item(report: Report, update: Any = None) -> widgets.Widget:
    objects: list[Any] = list(report.figures)
    objects.extend(str(extra) for extra in report.extra)
    children: list[widgets.Widget] = []
    # folded by default, so that only the plots are visible at first
    fit = _fit_results(report.table) if report.table else None
    if update is not None:
        # on the line of the fit results
        children.append(_row(fit, [update]))
    elif fit is not None:
        children.append(fit)
    if objects:
        children.append(_output(*objects))
    if not children:
        return _message("Empty report.")
    return widgets.VBox(children)


def show_reports(reports_: Any, updates: Updates | None = None) -> widgets.Widget:
    """Accordion of reports (figures and fit tables), one entry per target.

    Args:
        reports_: the ``reports`` attribute of an execution, or the execution
            itself.
        updates: the platform update of the execution, if any: each target
            gets an *Update* button, when the update applies per target.
    """
    if updates is None and isinstance(reports_, Completed):
        updates = reports_.updates
    items = (
        reports(reports_)
        if isinstance(reports_, QibocalCompleted)
        else reports_of(reports_)
    )
    per_target = updates is not None and updates.available and updates.per_target
    outputs = {
        layout.report_title(target): _report_item(
            report,
            update_button(updates, target)
            if per_target and target is not None
            else None,
        )
        for target, report in items.items()
    }
    if not outputs:
        return _message("No report to display.")
    return _accordion(outputs, expanded=layout.expanded(outputs))


def display(
    completed: QibocalCompleted,
    actions: Sequence[widgets.Widget] = (),
    total: float | None = None,
) -> widgets.Widget:
    """Full rendering of an execution: data and, when available, reports.

    Above them, a line with the protocol and its times (``total``, since
    submitted, for background executions), and buttons: the given
    ``actions``, and the platform update of a fitted execution (see
    ``Completed.update``).
    """
    updates = getattr(completed, "updates", None)
    buttons = list(actions)
    if updates is not None and updates.available:
        buttons.append(update_button(updates))
    title, times = layout.summary(completed, total)
    # with the profile, folded
    heading = ProfileView(completed, title, times)
    header = _row(heading, buttons, align="center")
    return widgets.VBox([header, _body(completed, updates)])


def _body(completed: QibocalCompleted, updates: Updates | None) -> widgets.Widget:
    sections: dict[str, widgets.Widget] = {}
    try:
        sections[layout.DATA] = show_data(completed.data)
    except ValueError:
        # no acquisition data (e.g. not yet loaded, or acquisition failed)
        pass
    if completed.reports is not None:
        sections[layout.REPORTS] = show_reports(completed.reports, updates)
    if completed.error is not None:
        sections[layout.ERROR] = widgets.HTML(
            f"<pre style='color: var(--jp-error-color1, red)'>{completed.error!r}</pre>"
        )
    if not sections:
        return _message("Nothing to display yet.")
    if len(sections) == 1:
        return next(iter(sections.values()))
    tabs = widgets.Tab(children=list(sections.values()))
    for index, title in enumerate(sections):
        tabs.set_title(index, title)
    tabs.selected_index = list(sections).index(layout.initial_section(sections))
    return tabs


class Jupyter(Frontend):
    """Display executions in Jupyter, with :func:`display`.

    Compatible with :class:`~qibocal_widgets.marimo.Marimo`: each
    frontend uses its own view.
    """

    protocol = MIMEBUNDLE

    def render(self, completed: QibocalCompleted) -> Any:
        return display(completed)

    def confirmable(self) -> bool:
        """In a kernel, where the *Run* button can be clicked."""
        return _kernel() is not None

    def render_pending(self, pending: Pending) -> Any:
        """A live view: the *Run* button, if waiting for confirmation, the
        progress (see :class:`ProgressView`), then the result, with a *Run
        again* button."""
        box = widgets.VBox([])

        def show(pending: Pending) -> None:
            if pending.status == DONE:
                box.children = [
                    display(
                        pending.result(),
                        actions=[again_button(pending)],
                        total=pending.elapsed,
                    )
                ]
            elif pending.status == FAILED:
                box.children = [
                    again_button(pending),
                    widgets.HTML(f"<pre>{pending.describe()}</pre>"),
                ]
            elif pending.status == READY:
                box.children = [run_button(pending)]
            elif not (box.children and isinstance(box.children[0], ProgressView)):
                # following the execution in place, on the kernel's thread
                box.children = [ProgressView(pending, schedule=_on_kernel)]

        show(pending)
        pending.on_change(lambda pending: _on_kernel(show, pending))
        return box


def _on_kernel(function: Any, *args: Any) -> None:
    """Run a function on the kernel's main thread, as soon as it is idle.

    Updates of a pending view come from background threads, but building
    widgets may capture displays into output widgets, which relies on hooks
    of the whole kernel: they are only safe on the main thread. Outside of a
    kernel, the function runs immediately.
    """
    loop = getattr(_kernel(), "io_loop", None)
    if loop is None:
        function(*args)
    else:
        loop.add_callback(function, *args)


def _kernel() -> Any:
    """The running IPython kernel, if any."""
    try:
        from IPython import get_ipython
    except ImportError:
        return None
    return getattr(get_ipython(), "kernel", None)


def wrap(completed: QibocalCompleted) -> Completed:
    """Make any execution display itself in Jupyter."""
    return Jupyter().attach(completed)
