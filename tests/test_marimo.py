import re

import pytest
from conftest import TARGETS

marimo = pytest.importorskip("marimo")

from marimo._output.formatting import get_formatter
from qibocal.auto.task import Completed as QibocalCompleted

from qibocal_widgets import Completed, Executor
from qibocal_widgets.marimo import (
    Marimo,
    display,
    show_data,
    show_reports,
    wrap,
)


def render(obj) -> str:
    """Render through marimo's own formatter machinery, as a cell would."""
    formatter = get_formatter(obj)
    assert formatter is not None
    mime, data = formatter(obj)
    assert mime == "text/html"
    return data


@pytest.fixture
def widget_executor():
    return Executor(None, targets=TARGETS, update=False, plugins=[Marimo()])


def test_executor_attaches_marimo_view(widget_executor, bound):
    completed = widget_executor(bound)
    assert "_display_" in completed.views
    assert "_display_" in widget_executor.acquire(bound).views


def test_display_protocol(widget_executor, bound):
    completed = widget_executor(bound)
    assert callable(completed._display_)

    html = render(completed)
    for target in TARGETS:
        assert f"Raw data: {target}" in html
        assert f"Target {target}" in html


def test_acquired_shows_only_data(widget_executor, bound):
    acquired = widget_executor.acquire(bound)
    html = render(acquired)
    assert "Raw data: 0" in html
    assert "Target 0" not in html


def expanded_items(html: str) -> list[str]:
    """Expanded state of every accordion, outermost first."""
    return re.findall(r"data-expanded='([^']*)'", html)


def test_reports_tab_selected(completed):
    tabs = display(completed)
    assert isinstance(tabs, marimo.ui.tabs)
    assert tabs.value == "Reports"


def test_data_tab_selected_without_reports(completed):
    """Without reports, the first available section is selected."""
    failed = wrap(completed)
    failed.reports = None
    failed.error = RuntimeError("boom")
    assert display(failed).value == "Data"


@pytest.mark.parametrize("show", [show_data, show_reports])
def test_single_target_expanded(single, completed, show):
    assert expanded_items(show(single).text)[0] == "[&quot;0&quot;]"
    assert expanded_items(show(completed).text)[0] == "[]"


def test_fit_results_folded_above_plot(single):
    html = show_reports(single).text
    # outer per-target accordion expanded, nested fit results folded
    assert expanded_items(html) == ["[&quot;0&quot;]", "[]"]
    assert html.index("Fit results") < html.index("marimo-plotly")
    # horizontally centered by mo.center (a column flexbox)
    assert "align-items: center" in html


def test_show_helpers(completed):
    assert isinstance(show_data(completed), marimo.Html)
    assert isinstance(show_data(completed.data), marimo.Html)
    assert isinstance(show_reports(completed), marimo.Html)
    assert isinstance(show_reports(completed.reports), marimo.Html)

    wrapped = wrap(completed)
    assert "Raw data: 1" in render(show_data(wrapped))
    assert "Target 1" in render(show_reports(wrapped))


def test_empty():
    assert "No acquired data" in render(show_data({}))
    assert "No report" in render(show_reports(None))
    assert "Nothing to display" in render(display(Completed()))


def test_error_section(completed):
    failed = wrap(completed)
    failed.error = RuntimeError("boom")
    failed.success = False
    assert "boom" in render(failed)


def test_wrap_plain(completed):
    assert type(completed) is QibocalCompleted
    assert "_display_" in wrap(completed).views
