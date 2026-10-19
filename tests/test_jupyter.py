import pytest
from conftest import TARGETS

widgets = pytest.importorskip("ipywidgets")

from qibocal.auto.task import Completed

from qibocal_widgets.jupyter import (
    JupyterCompleted,
    JupyterExecutor,
    display,
    show_data,
    show_reports,
    wrap,
)


def titles(container) -> list[str]:
    return [container.get_title(i) for i in range(len(container.children))]


@pytest.fixture
def widget_executor():
    return JupyterExecutor(None, targets=TARGETS, update=False)


def test_executor_returns_jupyter_completed(widget_executor, bound):
    completed = widget_executor(bound)
    assert isinstance(completed, JupyterCompleted)
    assert isinstance(widget_executor.acquire(bound), JupyterCompleted)


def test_display_protocol(widget_executor, bound):
    completed = widget_executor(bound)
    assert callable(completed._ipython_display_)

    widget = display(completed)
    assert isinstance(widget, widgets.Tab)
    assert titles(widget) == ["Data", "Reports"]
    data, reports = widget.children
    assert titles(data) == [f"Raw data: {t}" for t in TARGETS]
    assert titles(reports) == [f"Target {t}" for t in TARGETS]


def test_ipython_display_calls_display(widget_executor, bound, monkeypatch):
    completed = widget_executor(bound)
    shown = []
    monkeypatch.setattr("qibocal_widgets.jupyter.ipy_display", shown.append)
    completed._ipython_display_()
    # nested outputs also go through display(); the outermost widget is last
    assert isinstance(shown[-1], widgets.Tab)


def test_acquired_shows_only_data(widget_executor, bound):
    widget = display(widget_executor.acquire(bound))
    assert isinstance(widget, widgets.Accordion)
    assert titles(widget) == [f"Raw data: {t}" for t in TARGETS]


def test_show_helpers(completed):
    assert isinstance(show_data(completed), widgets.Accordion)
    assert isinstance(show_data(completed.data), widgets.Accordion)
    assert isinstance(show_reports(completed), widgets.Accordion)
    assert isinstance(show_reports(completed.reports), widgets.Accordion)

    wrapped = wrap(completed)
    assert isinstance(wrapped.show_data(), widgets.Accordion)
    assert isinstance(wrapped.show_reports(), widgets.Accordion)


def test_empty():
    assert "No acquired data" in show_data({}).value
    assert "No report" in show_reports(None).value
    assert "Nothing to display" in display(JupyterCompleted()).value


def test_error_section(completed):
    failed = wrap(completed)
    failed.error = RuntimeError("boom")
    failed.success = False
    widget = display(failed)
    assert titles(widget) == ["Data", "Reports", "Error"]
    assert "boom" in widget.children[-1].value


def test_wrap_plain(completed):
    assert type(completed) is Completed
    assert isinstance(wrap(completed), JupyterCompleted)
