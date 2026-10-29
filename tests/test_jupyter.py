import pytest
from conftest import TARGETS

widgets = pytest.importorskip("ipywidgets")

from qibocal.auto.task import Completed as QibocalCompleted

from qibocal_widgets import Completed, Executor
from qibocal_widgets.jupyter import (
    Jupyter,
    display,
    show_data,
    show_reports,
    wrap,
)


def titles(container) -> list[str]:
    return [container.get_title(i) for i in range(len(container.children))]


@pytest.fixture
def widget_executor():
    return Executor(None, targets=TARGETS, update=False, frontends=[Jupyter()])


def test_executor_attaches_jupyter_view(widget_executor, bound):
    completed = widget_executor(bound)
    assert "_repr_mimebundle_" in completed.views
    assert "_repr_mimebundle_" in widget_executor.acquire(bound).views


def test_display_protocol(widget_executor, bound):
    completed = widget_executor(bound)
    bundle = completed._repr_mimebundle_()
    assert "application/vnd.jupyter.widget-view+json" in bundle

    view = display(completed)
    assert isinstance(view, widgets.VBox)
    buttons, widget = view.children
    # update=False: offered, to apply after looking at the fit
    assert [b.label for b in buttons.children] == ["⤓ Update all targets"]
    assert isinstance(widget, widgets.Tab)
    assert titles(widget) == ["Data", "Reports"]
    data, reports = widget.children
    assert titles(data) == [f"Raw data: {t}" for t in TARGETS]
    assert titles(reports) == [f"Target {t}" for t in TARGETS]


def test_mimebundle_renders_display(widget_executor, bound, monkeypatch):
    completed = widget_executor(bound)
    shown = []

    def spy(c):
        shown.append(display(c))
        return shown[-1]

    monkeypatch.setitem(completed.views, "_repr_mimebundle_", spy)
    bundle = completed._repr_mimebundle_()
    (widget,) = shown
    assert isinstance(widget, widgets.VBox)
    assert bundle["application/vnd.jupyter.widget-view+json"]["model_id"] == (
        widget.model_id
    )


def test_acquired_shows_only_data(widget_executor, bound):
    widget = display(widget_executor.acquire(bound))
    assert isinstance(widget, widgets.Accordion)
    assert titles(widget) == [f"Raw data: {t}" for t in TARGETS]


def test_reports_tab_selected(completed):
    tabs = display(completed)
    assert tabs.get_title(tabs.selected_index) == "Reports"


def test_data_tab_selected_without_reports(completed):
    """Without reports, the first available section is selected."""
    failed = wrap(completed)
    failed.reports = None
    failed.error = RuntimeError("boom")
    tabs = display(failed)
    assert tabs.get_title(tabs.selected_index) == "Data"


@pytest.mark.parametrize("show", [show_data, show_reports])
def test_single_target_expanded(single, completed, show):
    assert show(single).selected_index == 0
    assert show(completed).selected_index is None


def test_fit_results_folded_above_plot(single):
    (item,) = show_reports(single).children
    assert isinstance(item, widgets.VBox)
    fit, plots = item.children
    # nested fit results come first, folded, and centered
    assert isinstance(fit, widgets.Accordion)
    assert titles(fit) == ["Fit results"]
    assert fit.selected_index is None
    (centered,) = fit.children
    assert centered.layout.justify_content == "center"
    assert "<table>" in centered.children[0].value
    assert isinstance(plots, widgets.Output)


def test_show_helpers(completed):
    assert isinstance(show_data(completed), widgets.Accordion)
    assert isinstance(show_data(completed.data), widgets.Accordion)
    assert isinstance(show_reports(completed), widgets.Accordion)
    assert isinstance(show_reports(completed.reports), widgets.Accordion)

    wrapped = wrap(completed)
    assert isinstance(show_data(wrapped), widgets.Accordion)
    assert isinstance(show_reports(wrapped), widgets.Accordion)


def test_empty():
    assert "No acquired data" in show_data({}).value
    assert "No report" in show_reports(None).value
    assert "Nothing to display" in display(Completed()).value


def test_error_section(completed):
    failed = wrap(completed)
    failed.error = RuntimeError("boom")
    failed.success = False
    widget = display(failed)
    assert titles(widget) == ["Data", "Reports", "Error"]
    assert "boom" in widget.children[-1].value


def test_wrap_plain(completed):
    assert type(completed) is QibocalCompleted
    assert "_repr_mimebundle_" in wrap(completed).views
