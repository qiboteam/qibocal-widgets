"""Platform updates for one execution only (``platform_updates``)."""

import json

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import create_calibration_platform

from qibocal_widgets import Executor

PATH = "configs.0/drive.frequency"
FULL = f"parameters.{PATH}"


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    return create_calibration_platform("mock")


def test_blocking(platform, tmp_path):
    executor = Executor(platform, path=tmp_path / "s", targets=TARGETS, update=False)
    before = executor.platform_state[FULL]
    completed = executor(fake(npoints=3), platform_updates={PATH: 4.5e9})
    assert completed.data.scale[0] == 4.5e9  # acquired with it
    assert completed.data.scale[1] != 4.5e9
    assert executor.platform_state[FULL] == before  # restored
    assert len(executor.history) == 0  # the platform did not change
    recorded = json.loads((completed.path / "platform-updates.json").read_text())
    assert recorded == {FULL: 4.5e9}  # by full path
    report = completed.profile_report()
    assert f"temporary platform updates: {FULL} = 4500000000.0" in report


def test_submit_and_reuse(platform):
    executor = Executor(platform, targets=TARGETS, update=False)
    first = executor.submit(fake(npoints=3), reuse=True, platform_updates={PATH: 4.5e9})
    same = executor.submit(
        fake(npoints=3), reuse=True, platform_updates={FULL: 4.5e9}
    )  # the same path, written in full
    assert same is first
    other = executor.submit(fake(npoints=3), reuse=True, platform_updates={PATH: 4.6e9})
    plain = executor.submit(fake(npoints=3), reuse=True)
    assert other is not first and plain is not first
    assert first.result(10).data.scale[0] == 4.5e9
    assert other.result(10).data.scale[0] == 4.6e9
    assert plain.result(10).data.scale[0] == executor.platform_state[FULL]
    assert first.platform_updates == {FULL: 4.5e9}


def test_invalid(platform):
    executor = Executor(platform, targets=TARGETS, update=False)
    with pytest.raises(KeyError):
        executor.submit(fake(npoints=3), platform_updates={"configs.nowhere": 1})
    with pytest.raises(ValueError, match="platform state"):
        Executor(None, targets=TARGETS).submit(
            fake(npoints=3), platform_updates={PATH: 1}
        )
