"""The platform state explorer, driven as the browser side would."""

import pytest
from conftest import PLATFORMS
from qibocal import create_calibration_platform

pytest.importorskip("anywidget")

from qibocal_widgets import PlatformState
from qibocal_widgets._core.explorer import format_value
from qibocal_widgets.explorer import Explorer

FREQUENCY = "parameters.configs.0/drive.frequency"


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    return PlatformState.of(create_calibration_platform("mock"), name="state")


def keys(explorer):
    return [row["key"] for row in explorer.rows]


def send(explorer, **content):
    explorer._message(explorer, content, [])


def test_root(state):
    explorer = state.explore()
    assert isinstance(explorer, Explorer)
    assert keys(explorer) == ["parameters", "calibration"]
    assert all(row["kind"] == "branch" for row in explorer.rows)
    assert explorer.crumbs == [{"label": "state", "path": ""}]


def test_navigate(state):
    explorer = state.explore("configs.0/drive")
    assert explorer.path == "parameters.configs.0/drive"
    assert "frequency" in keys(explorer)
    assert [c["label"] for c in explorer.crumbs] == [
        "state",
        "parameters",
        "configs",
        "0/drive",
    ]
    # a leaf shows its parent, where it can be copied
    send(explorer, kind="navigate", text=f'state["{FREQUENCY}"]')
    assert explorer.path == "parameters.configs.0/drive"
    row = next(r for r in explorer.rows if r["key"] == "frequency")
    assert row["path"] == FREQUENCY
    assert row["display"].endswith("GHz")


def test_search(state):
    explorer = state.explore()
    send(explorer, kind="navigate", text="frequency_01")
    assert explorer.query == "frequency_01"
    assert explorer.rows
    assert all("frequency_01" in row["path"] for row in explorer.rows)
    assert all(row["key"] == row["path"] for row in explorer.rows)


def test_edit(state):
    explorer = state.explore("configs.0/drive", editable=True)
    send(explorer, kind="edit", path=FREQUENCY, value="4.25e9")
    assert explorer.error == ""
    assert state[FREQUENCY] == 4.25e9
    assert explorer.snippet == f'state.update({{"{FREQUENCY}": 4250000000.0}})'
    row = next(r for r in explorer.rows if r["key"] == "frequency")
    assert row["raw"] == "4250000000.0"


@pytest.mark.parametrize(
    "value,message",
    [("4.2 GHz", "Not valid JSON"), ('"text"', "Invalid platform state")],
)
def test_edit_errors(state, value, message):
    explorer = state.explore(editable=True)
    before = state[FREQUENCY]
    send(explorer, kind="edit", path=FREQUENCY, value=value)
    assert message in explorer.error
    assert state[FREQUENCY] == before


def test_readonly(state):
    snapshot = state.snapshot()
    explorer = snapshot.explore(editable=True)
    assert not explorer.editable
    send(explorer, kind="edit", path=FREQUENCY, value="1.0")
    assert "disabled" in explorer.error


def test_compare(state):
    start = state.snapshot()
    state.update({FREQUENCY: 4.4e9})
    explorer = state.explore(compare=start)
    assert explorer.comparing
    parameters = next(r for r in explorer.rows if r["key"] == "parameters")
    assert parameters["changed"] and "1 changed" in parameters["display"]
    send(explorer, kind="navigate", text=FREQUENCY)
    row = next(r for r in explorer.rows if r["key"] == "frequency")
    assert row["changed"] and row["before"] == format_value(start[FREQUENCY])
    explorer.changed_only = True
    assert keys(explorer) == ["frequency"]


def test_refresh(state):
    explorer = state.explore("configs.0/drive")
    state.update({FREQUENCY: 4.9e9})
    send(explorer, kind="refresh")
    row = next(r for r in explorer.rows if r["key"] == "frequency")
    assert row["raw"] == "4900000000.0"


@pytest.mark.parametrize(
    "value,text",
    [
        (None, "null"),
        (True, "true"),
        (1000, "1,000"),
        (4.2e9, "4.2 GHz"),
        (5.5e6, "5.5 MHz"),
        (2500.0, "2.5 kHz"),
        (3e-6, "3.000e-06"),
        (0.25, "0.25"),
        ([0.1, None], "[0.1, null]"),
        ("RX", "RX"),
    ],
)
def test_format(value, text):
    assert format_value(value) == text


def test_frontends(state):
    """The same widget is displayed by both frontends."""
    explorer = state.explore()
    bundle = explorer._repr_mimebundle_()
    data = bundle[0] if isinstance(bundle, tuple) else bundle
    assert "application/vnd.jupyter.widget-view+json" in data
    marimo = pytest.importorskip("marimo")
    from marimo._output.formatting import get_formatter

    assert get_formatter(explorer) is not None
    assert marimo is not None
