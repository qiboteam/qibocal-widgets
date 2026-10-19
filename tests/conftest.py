"""Shared fixtures: a fake protocol exercising the full Qibocal phase chain.

No platform is required: the executor is created without one, and the protocol
callbacks only declare the context they need.
"""

from dataclasses import dataclass, field

import numpy as np
import plotly.graph_objects as go
import pytest
from qibocal import Executor
from qibocal.auto.operation import Data, Parameters, Protocol, Results

TARGETS = [0, 1]
NPOINTS = 7

RecordType = np.dtype([("signal", np.float64), ("phase", np.float64)])


@dataclass
class FakeParameters(Parameters):
    npoints: int = NPOINTS


@dataclass
class FakeData(Data):
    frequencies: dict[int, list[float]] = field(default_factory=dict)
    """Sweep coordinate stored outside the records, as spectroscopies do."""
    scale: dict[int, float] = field(default_factory=dict)
    """A per-target scalar, which must not become a column."""
    data: dict[int, np.ndarray] = field(default_factory=dict)


@dataclass
class FakeResults(Results):
    peak: dict[int, float] = field(default_factory=dict)


def _acquisition(params: FakeParameters, targets: list[int]) -> FakeData:
    data = FakeData()
    for target in targets:
        signal = np.linspace(0, 1, params.npoints) + target
        data.register_qubit(
            RecordType, target, {"signal": signal, "phase": np.zeros_like(signal)}
        )
        data.frequencies[target] = list(np.arange(params.npoints) * 1e6)
        data.scale[target] = 2.0
    return data


def _fit(data: FakeData) -> FakeResults:
    return FakeResults(peak={t: float(np.max(data[t].signal)) for t in data.qubits})


def _report(
    data: FakeData, results: FakeResults, target: int
) -> tuple[list[go.Figure], str]:
    figure = go.Figure(go.Scatter(x=data.frequencies[target], y=data[target].signal))
    table = f"<table><tr><td>peak</td><td>{results.peak[target]}</td></tr></table>"
    return [figure], table


@pytest.fixture
def protocol() -> Protocol:
    return Protocol(_acquisition, _fit, _report, None)


@pytest.fixture
def bound(protocol):
    return protocol(npoints=NPOINTS)


@pytest.fixture
def executor() -> Executor:
    return Executor(None, targets=TARGETS, update=False)


@pytest.fixture
def completed(executor, bound):
    """A fully executed (acquired, fitted, reported) plain execution."""
    return executor(bound)


@pytest.fixture
def acquired(executor, bound):
    """An execution stopped after acquisition."""
    return executor.acquire(bound)
