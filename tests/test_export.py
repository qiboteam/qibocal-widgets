"""Writing the platform state back to a platform folder (``save``)."""

import json
import shutil
import subprocess

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import create_calibration_platform

from qibocal_widgets import Executor, PlatformState


@pytest.fixture
def platforms(tmp_path, monkeypatch):
    """A copy of the test platforms, as QIBOLAB_PLATFORMS."""
    folder = tmp_path / "platforms"
    shutil.copytree(PLATFORMS, folder)
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(folder))
    return folder


def test_formatted_as_qibolab(platforms, tmp_path):
    platform = create_calibration_platform("mock")
    folder = tmp_path / "dump"
    PlatformState.of(platform).save(folder)
    expected = tmp_path / "expected"
    expected.mkdir()
    platform.dump(expected)
    platform.calibration.dump(expected)
    for name in ("parameters.json", "calibration.json"):
        assert (folder / name).read_text() == (expected / name).read_text()


def test_platform_folder(platforms):
    platform = create_calibration_platform("mock")
    executor = Executor(platform, targets=TARGETS, update=False)
    completed = executor(fake(npoints=3))
    completed.update([0])
    path = executor.platform_state.save(overwrite=True)
    assert path == str(platforms / "mock")
    parameters = json.loads((platforms / "mock" / "parameters.json").read_text())
    drive = platform.qubits[0].drive
    assert parameters["configs"][drive]["frequency"] == completed.results.peak[0] * 1e9
    # the saved folder is the platform, as created again
    again = create_calibration_platform("mock")
    assert again.config(drive).frequency == completed.results.peak[0] * 1e9


def test_not_replaced_outside_git(platforms):
    state = PlatformState.of(create_calibration_platform("mock"))
    with pytest.raises(FileExistsError, match="overwrite=True"):
        state.save()
    assert state.save(overwrite=True) == str(platforms / "mock")


def test_replaced_in_git(platforms):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    subprocess.run(["git", "init", "-q", str(platforms)], check=True)
    state = PlatformState.of(create_calibration_platform("mock"))
    assert state.save() == str(platforms / "mock")


def test_new_folder(tmp_path, platforms):
    state = PlatformState.of(create_calibration_platform("mock")).snapshot()
    folder = tmp_path / "new" / "chip"
    assert state.save(folder) == str(folder)
    assert PlatformState.load(folder).diff(state) == {}


def test_unknown_folder():
    snapshot = PlatformState.frozen({"parameters": "{}", "calibration": None})
    with pytest.raises(ValueError, match="give a path"):
        snapshot.save()
    with pytest.raises(LookupError, match="not known"):
        Executor(None).platform_state.save()  # no state at all
