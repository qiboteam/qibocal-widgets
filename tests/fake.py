"""A fake protocol exercising the full Qibocal phase chain.

It is defined in an importable module, so that remote workers can resolve it
by reference (``fake:fake``), as they would for any external protocol.

No platform is required: the callbacks only declare the context they need, and
the acquisition only reads the platform when available.
"""

from dataclasses import dataclass, field

import numpy as np
import plotly.graph_objects as go
from qibocal.auto.operation import Data, Parameters, Protocol, Results

NPOINTS = 7
DEFAULT_SCALE = 2.0

RecordType = np.dtype([("signal", np.float64), ("phase", np.float64)])


@dataclass
class FakeParameters(Parameters):
    npoints: int = NPOINTS


@dataclass
class FakeData(Data):
    frequencies: dict[int, list[float]] = field(default_factory=dict)
    """Sweep coordinate stored outside the records, as spectroscopies do."""
    scale: dict[int, float] = field(default_factory=dict)
    """A per-target scalar, which must not become a column.

    The drive frequency of the target, when acquired with a platform.
    """
    data: dict[int, np.ndarray] = field(default_factory=dict)


@dataclass
class FakeResults(Results):
    peak: dict[int, float] = field(default_factory=dict)


def drive_frequency(platform, target) -> float:
    return platform.config(platform.qubits[target].drive).frequency


def _acquisition(params: FakeParameters, platform, targets: list[int]) -> FakeData:
    data = FakeData()
    for target in targets:
        signal = np.linspace(0, 1, params.npoints) + target
        data.register_qubit(
            RecordType, target, {"signal": signal, "phase": np.zeros_like(signal)}
        )
        data.frequencies[target] = list(np.arange(params.npoints) * 1e6)
        data.scale[target] = (
            DEFAULT_SCALE if platform is None else drive_frequency(platform, target)
        )
    return data


def _fit(data: FakeData) -> FakeResults:
    return FakeResults(peak={t: float(np.max(data[t].signal)) for t in data.qubits})


def _report(
    data: FakeData, results: FakeResults, target: int
) -> tuple[list[go.Figure], str]:
    figure = go.Figure(go.Scatter(x=data.frequencies[target], y=data[target].signal))
    table = f"<table><tr><td>peak</td><td>{results.peak[target]}</td></tr></table>"
    return [figure], table


def _update(results: FakeResults, platform, target: int):
    """Set the drive frequency, in GHz, to the fitted peak."""
    drive = platform.qubits[target].drive
    platform.update({f"configs.{drive}.frequency": results.peak[target] * 1e9})


fake = Protocol(_acquisition, _fit, _report, _update)
