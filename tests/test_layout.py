"""The layout of the platform (``executor.describe_platform``)."""

import json

import pytest
from conftest import PLATFORMS, TARGETS
from qibocal import create_calibration_platform

from qibocal_widgets import Executor, PlatformLayout


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    return create_calibration_platform("mock")


def test_local(platform):
    layout = Executor(platform, targets=TARGETS).describe_platform()
    assert isinstance(layout, PlatformLayout)
    assert layout.qubits[0]["drive"] == "0/drive"  # integer ids kept
    assert 1 in layout.couplers
    drive = layout.channels["0/drive"]
    assert drive["kind"] == "IqChannel" and drive["lo"] == "0/drive_lo"
    assert layout.channels["0/acquisition"]["probe"] == "0/probe"
    assert layout.instruments["twpa_pump"]["kind"] == "DummyLocalOscillator"


def test_lo(platform):
    executor = Executor(platform, targets=TARGETS)
    layout = executor.describe_platform()
    path = layout.lo_config(layout.qubits[0]["drive"])
    assert path == "parameters.configs.0/drive_lo"
    # the cross-drive too: changing it affects all of them
    assert sorted(layout.sharing(path)) == ["0/drive", "0/drive12", "01/drive"]
    assert layout.lo_config("0/flux") is None
    executor.platform_state[f"{path}.frequency"] = 4.3e9
    assert platform.config("0/drive_lo").frequency == 4.3e9


def test_no_platform():
    with pytest.raises(ValueError, match="No platform"):
        Executor(None).describe_platform()


def test_json_roundtrip(platform):
    from qibocal_widgets._core.remote.worker import layout_of

    document = json.loads(json.dumps(layout_of(platform)))
    assert PlatformLayout.from_json(document) == PlatformLayout.of(platform)
