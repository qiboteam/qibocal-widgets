import numpy as np
import plotly.graph_objects as go
import pytest
from conftest import NPOINTS, TARGETS

from qibocal_widgets import Report, data_frames, reports, reports_of
from qibocal_widgets._core.data import label


def test_data_frames_from_records(acquired):
    frames = data_frames(acquired.data)

    assert set(frames) == set(TARGETS)
    for target, frame in frames.items():
        assert len(frame) == NPOINTS
        # record fields become columns
        assert {"signal", "phase"} <= set(frame.columns)
        # per-target sequences of matching length are attached as columns
        assert "frequencies" in frame.columns
        # per-target scalars are not
        assert "scale" not in frame.columns
        np.testing.assert_allclose(frame["signal"].min(), target)


def test_data_frames_from_complex_dict():
    values = np.exp(1j * np.linspace(0, np.pi, 5))
    frames = data_frames({0: values})

    assert set(frames[0].columns) == {"real", "imag", "signal", "phase"}
    np.testing.assert_allclose(frames[0]["signal"], 1.0)


def test_data_frames_plain_arrays():
    frames = data_frames({"a": np.arange(3), "b": np.ones((2, 3))})

    assert list(frames["a"].columns) == ["value"]
    assert frames["b"].shape == (2, 3)


def test_data_frames_unsupported():
    assert data_frames(object()) == {}
    assert data_frames({0: object()}) == {}


def test_reports_per_target(completed):
    items = reports(completed)

    assert set(items) == set(TARGETS)
    for report in items.values():
        assert isinstance(report, Report)
        assert len(report.figures) == 1
        assert isinstance(report.figures[0], go.Figure)
        assert "<table>" in report.table
        assert report.extra == []


def test_reports_missing(acquired):
    assert reports(acquired) == {}


def test_reports_of_none():
    assert reports_of(None) == {}


@pytest.mark.parametrize(
    "value,figures,table,extra",
    [
        (go.Figure(), 1, "", []),
        ([go.Figure(), go.Figure()], 2, "", []),
        (([go.Figure()], "<b>x</b>"), 1, "<b>x</b>", []),
        (("<a>", "<b>"), 0, "<a><b>", []),
        ((go.Figure(), 42), 1, "", [42]),
    ],
)
def test_reports_of_single(value, figures, table, extra):
    items = reports_of(value)

    assert set(items) == {None}
    report = items[None]
    assert len(report.figures) == figures
    assert report.table == table
    assert report.extra == extra


def test_reports_of_passthrough():
    report = Report()
    assert reports_of({0: report})[0] is report


def test_label():
    assert label(3) == "3"
    assert label((0, 1)) == "0-1"
    assert label("q0") == "q0"
