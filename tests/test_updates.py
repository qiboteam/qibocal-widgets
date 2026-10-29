"""Approving platform updates after looking at the fit (``completed.update``)."""

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import create_calibration_platform

from qibocal_widgets import Executor


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    return create_calibration_platform("mock")


def frequency(platform, target):
    return platform.config(platform.qubits[target].drive).frequency


def test_per_target(platform, tmp_path):
    before = {t: frequency(platform, t) for t in TARGETS}
    executor = Executor(platform, path=tmp_path / "s", targets=TARGETS, update=False)
    completed = executor(fake(npoints=3))
    assert {t: frequency(platform, t) for t in TARGETS} == before  # not applied
    assert completed.updates.pending == TARGETS

    assert completed.update([0]) == [0]
    assert frequency(platform, 0) == completed.results.peak[0] * 1e9
    assert frequency(platform, 1) == before[1]
    assert completed.update() == [1]  # the remaining ones
    assert frequency(platform, 1) == completed.results.peak[1] * 1e9
    assert completed.update() == []  # nothing left
    assert (tmp_path / "s" / "new_platform").is_dir()  # recorded


def test_applied_automatically(platform):
    executor = Executor(platform, targets=TARGETS, update=True)
    completed = executor(fake(npoints=3))
    assert completed.updates.pending == []
    assert completed.update() == []


def test_errors(platform):
    executor = Executor(platform, targets=TARGETS, update=False)
    with pytest.raises(ValueError, match="Not targets"):
        executor(fake(npoints=3)).update([7])
    with pytest.raises(ValueError, match="not a fitted execution"):
        executor.acquire(fake(npoints=3)).update()


def test_pending(platform):
    executor = Executor(platform, targets=TARGETS, update=False)
    pending = executor.submit(fake(npoints=3))
    pending.result(10)
    assert pending.update() == TARGETS
    assert frequency(platform, 0) == pending().results.peak[0] * 1e9


def test_pending_not_done():
    from fake import fake as protocol

    class Never(Executor):
        def _launch(self, *args, **kwargs):
            pass  # never starts

    pending = Never(None, targets=TARGETS).submit(protocol(npoints=3))
    with pytest.raises(ValueError, match="nothing to update yet"):
        pending.update()


def test_buttons(platform):
    pytest.importorskip("anywidget")
    from qibocal_widgets._core.button import update_button

    executor = Executor(platform, targets=TARGETS, update=False)
    updates = executor(fake(npoints=3)).updates
    bulk, first, second = (
        update_button(updates),
        update_button(updates, 0),
        update_button(updates, 1),
    )
    assert (bulk.label, first.label) == ("⤓ Update all targets", "⤓ Update")
    first.click()
    assert (first.label, first.disabled) == ("✓ Applied", True)
    assert second.label == "⤓ Update" and bulk.label == "⤓ Update all targets"
    bulk.click()
    assert (bulk.label, second.label) == ("✓ All applied", "✓ Applied")
    assert bulk.disabled and second.disabled


def test_button_failure(platform, monkeypatch):
    pytest.importorskip("anywidget")
    from qibocal_widgets._core.button import update_button

    executor = Executor(platform, targets=TARGETS, update=False)
    updates = executor(fake(npoints=3)).updates

    def broken(*args, **kwargs):
        raise RuntimeError("unreachable")

    monkeypatch.setattr(executor, "update", broken)
    button = update_button(updates)
    button.click()
    assert button.label == "⚠ Update failed: retry"
    assert "unreachable" in button.tooltip and not button.disabled
    monkeypatch.undo()
    button.click()
    assert button.label == "✓ All applied"


def test_whole_update(platform):
    """Updates not taking a target apply to all targets at once."""
    from fake import _acquisition, _fit, _report
    from qibocal.auto.operation import Protocol

    def _update(results, platform):
        platform.update({"configs.0/drive.frequency": 4.2e9})

    whole = Protocol(_acquisition, _fit, _report, _update)
    executor = Executor(platform, targets=TARGETS, update=False)
    completed = executor(whole(npoints=3))
    assert not completed.updates.per_target
    with pytest.raises(ValueError, match="all targets at once"):
        completed.update([0])
    assert completed.update() == TARGETS
    assert completed.updates.pending == []
