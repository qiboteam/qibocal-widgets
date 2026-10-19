import pytest
from conftest import TARGETS

marimo = pytest.importorskip("marimo")

from marimo._output.formatting import get_formatter
from qibocal.auto.task import Completed

from qibocal_widgets.marimo import (
    MarimoCompleted,
    MarimoExecutor,
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
    return MarimoExecutor(None, targets=TARGETS, update=False)


def test_executor_returns_marimo_completed(widget_executor, bound):
    completed = widget_executor(bound)
    assert isinstance(completed, MarimoCompleted)
    assert isinstance(widget_executor.acquire(bound), MarimoCompleted)


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


def test_show_helpers(completed):
    assert isinstance(show_data(completed), marimo.Html)
    assert isinstance(show_data(completed.data), marimo.Html)
    assert isinstance(show_reports(completed), marimo.Html)
    assert isinstance(show_reports(completed.reports), marimo.Html)

    wrapped = wrap(completed)
    assert "Raw data: 1" in render(wrapped.show_data())
    assert "Target 1" in render(wrapped.show_reports())


def test_empty():
    assert "No acquired data" in render(show_data({}))
    assert "No report" in render(show_reports(None))
    assert "Nothing to display" in render(display(MarimoCompleted()))


def test_error_section(completed):
    failed = wrap(completed)
    failed.error = RuntimeError("boom")
    failed.success = False
    assert "boom" in render(failed)


def test_wrap_plain(completed):
    assert type(completed) is Completed
    assert isinstance(wrap(completed), MarimoCompleted)
