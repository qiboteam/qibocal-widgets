"""Exploring and updating platform states by path."""

import json

import pytest
from conftest import PLATFORMS, TARGETS
from qibocal import create_calibration_platform

from qibocal_widgets import Executor, PlatformState, ReadOnlyState
from qibocal_widgets._core.state import is_leaf

FREQUENCY = "parameters.configs.0/drive.frequency"
QUBIT = "calibration.single_qubits.0.qubit.frequency_01"


@pytest.fixture(autouse=True)
def mock(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))


@pytest.fixture
def platform():
    return create_calibration_platform("mock")


@pytest.fixture
def state(platform):
    return PlatformState.of(platform, name="state")


def drive(platform):
    return platform.config(platform.qubits[0].drive).frequency


def test_leaves():
    assert is_leaf(1.0) and is_leaf("a") and is_leaf(None)
    assert is_leaf([0.1, 0.2]) and is_leaf([]) and is_leaf([1, None])
    assert not is_leaf({"a": 1}) and not is_leaf([{"a": 1}]) and not is_leaf([True])


def test_get(state, platform):
    assert state[FREQUENCY] == drive(platform)
    assert FREQUENCY in state
    assert "parameters.nowhere" not in state
    assert state.get("parameters.nowhere", 42) == 42
    with pytest.raises(KeyError):
        state["parameters.nowhere"]


@pytest.mark.parametrize(
    "text",
    [
        FREQUENCY,
        "configs.0/drive.frequency",  # as in the dashboard, or Platform.update
        f'executor.platform_state["{FREQUENCY}"]',  # pasted code
        f"{{'{FREQUENCY}': 4.1e9}}",  # pasted output
    ],
)
def test_resolve(state, text):
    assert state.resolve(text) == FREQUENCY


def test_resolve_calibration(state):
    assert state.resolve("single_qubits.0.qubit.frequency_01") == QUBIT
    assert state.resolve("") == ""
    assert state.resolve("no.such.thing") is None


def test_pairs_and_lists(state):
    pair = state["parameters.native_gates.two_qubit.0-1"]
    assert isinstance(pair, dict)
    leaves = state.leaves("parameters.native_gates.single_qubit.0")
    # numeric segments index lists, as in Platform.update
    assert any(".0." in path or path.endswith(".0") for path in leaves)


def test_find(state):
    found = state.find("FREQUENCY_01")
    assert QUBIT in found
    assert all("frequency_01" in path for path in found)


def test_update(state, platform):
    state.update({FREQUENCY: 4.123e9, QUBIT: 4.1e9})
    assert drive(platform) == 4.123e9
    assert platform.calibration.single_qubits[0].qubit.frequency_01 == 4.1e9
    state["configs.0/drive.frequency"] = 4.2e9  # any accepted form
    assert drive(platform) == 4.2e9


def test_update_is_atomic_and_validated(state, platform):
    before = drive(platform)
    with pytest.raises(ValueError, match="Invalid"):
        state.update({FREQUENCY: 4.3e9, QUBIT: "not a number"})
    assert drive(platform) == before
    with pytest.raises(KeyError):
        state.update({"parameters.configs.0/drive.frequenzy": 1.0})  # no typos
    with pytest.raises(KeyError):
        state.update({"parameters": {}})  # whole documents are not values


def test_snapshot_and_diff(state):
    start = state.snapshot()
    assert start.readonly and not state.readonly
    with pytest.raises(ReadOnlyState):
        start.update({FREQUENCY: 1.0})
    state.update({FREQUENCY: 4.5e9})
    assert start[FREQUENCY] != 4.5e9
    assert state.diff(start) == {FREQUENCY: (start[FREQUENCY], 4.5e9)}
    assert start.diff(start) == {}


def test_load(tmp_path, state):
    from qibocal_widgets._core import platforms

    session = tmp_path / "session"
    platforms.write(state.state(), session / "platform")
    state.update({FREQUENCY: 4.6e9})
    platforms.write(state.state(), session / "new_platform")
    assert PlatformState.load(session)[FREQUENCY] == 4.6e9  # latest
    assert PlatformState.load(session / "platform")[FREQUENCY] != 4.6e9
    with pytest.raises(FileNotFoundError):
        PlatformState.load(tmp_path / "empty")


def test_unknown():
    state = Executor(None).platform_state
    with pytest.raises(LookupError):
        state.documents()
    assert "unknown" in repr(state)


def test_executor_state_recorded(tmp_path):
    path = tmp_path / "session"
    executor = Executor.create(path, platform="mock", targets=TARGETS)
    state = executor.platform_state
    assert state.name == "executor.platform_state"
    with executor:
        pass  # starts the session
    state.update({FREQUENCY: 4.7e9})
    assert drive(executor.platform) == 4.7e9
    recorded = json.loads((path / "new_platform" / "parameters.json").read_text())
    assert recorded["configs"]["0/drive"]["frequency"] == 4.7e9
    # and the session start is still what it was
    assert PlatformState.load(path / "platform")[FREQUENCY] != 4.7e9


def test_repr(state):
    assert repr(state).startswith("<PlatformState state (bound, ")
    assert "snapshot" in repr(state.snapshot())
