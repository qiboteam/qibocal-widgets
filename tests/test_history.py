"""History of the platform states (``executor.history``)."""

import json

import pytest
from conftest import PLATFORMS, TARGETS
from fake import fake
from qibocal import create_calibration_platform, protocols

from qibocal_widgets import Executor, Session
from qibocal_widgets._core import platforms as platforms_
from qibocal_widgets._core.history import FILE, _changes, _put, _remove

DRIVE0 = "parameters.configs.0/drive.frequency"
DRIVE1 = "parameters.configs.1/drive.frequency"


@pytest.fixture
def platform(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))
    return create_calibration_platform("mock")


@pytest.fixture
def executor(platform, tmp_path):
    return Executor(platform, path=tmp_path / "s", targets=TARGETS, update=False)


def test_updates_and_edits(executor):
    assert len(executor.history) == 0
    start = executor.platform_state[DRIVE0]
    completed = executor(fake(npoints=3))
    assert len(executor.history) == 0  # nothing applied yet
    completed.update([0])
    start_entry, update = executor.history.entries
    assert (start_entry.kind, update.kind) == ("start", "update")
    assert update.parent == 0 and update.task == "fake-0" and update.targets == [0]
    assert update.changes == {DRIVE0: (start, completed.results.peak[0] * 1e9)}
    assert update.describe() == "update fake-0 (0)"

    executor.platform_state[DRIVE1] = 4.5e9
    edit = executor.history[-1]
    assert (edit.kind, edit.parent) == ("edit", 1)
    assert list(edit.changes) == [DRIVE1]
    assert executor.history["fake-0"] == update


def test_states_and_diff(executor):
    start = executor.platform_state.snapshot()
    executor.platform_state[DRIVE0] = 4.1e9
    executor.platform_state[DRIVE1] = 4.25e9
    history = executor.history
    assert history.state(0).diff(start) == {}
    assert history.state(-1).diff(executor.platform_state.snapshot()) == {}
    assert history.diff(1, 2) == {DRIVE1: (start[DRIVE1], 4.25e9)}
    assert set(history.diff(0)) == {DRIVE0, DRIVE1}  # since the start
    assert history.diff(-1) == {}


def test_external_changes(executor, platform):
    executor.platform_state[DRIVE0] = 4.1e9
    platforms_.apply(
        platform,
        {
            "parameters": json.dumps(
                {
                    **json.loads(platform.parameters.model_dump_json()),
                    "settings": {"nshots": 7, "relaxation_time": 0},
                }
            )
        },
    )  # behind the executor's back
    executor.platform_state[DRIVE1] = 4.2e9
    kinds = [entry.kind for entry in executor.history]
    assert kinds == ["start", "edit", "external", "edit"]
    assert executor.history[2].changes == {"parameters.settings.nshots": (1024, 7)}


def test_restore_forks(executor):
    start = executor.platform_state.snapshot()
    executor.platform_state[DRIVE0] = 4.1e9  # 1
    executor.platform_state[DRIVE1] = 4.25e9  # 2
    restored = executor.history.restore(0)
    assert (restored.kind, restored.parent, restored.source) == ("restore", 0, 0)
    assert restored.changes == {}
    assert executor.platform_state.snapshot().diff(start) == {}
    executor.platform_state[DRIVE1] = 4.3e9  # continuing from the start
    assert [e.id for e in executor.history.lineage()] == [0, 3, 4]
    # the fork does not have the change of 1
    assert executor.history.diff(2, 4) == {
        DRIVE0: (4.1e9, start[DRIVE0]),
        DRIVE1: (4.25e9, 4.3e9),
    }
    assert len(executor.history) == 5  # nothing lost


def test_restore_paths(executor):
    start = executor.platform_state.snapshot()
    executor.platform_state.update({DRIVE0: 4.1e9, DRIVE1: 4.25e9})
    entry = executor.history.restore(0, ["configs.0/drive"])  # a branch
    assert entry.paths == ["configs.0/drive"] and entry.parent == 1
    assert executor.platform_state[DRIVE0] == start[DRIVE0]
    assert executor.platform_state[DRIVE1] == 4.25e9
    with pytest.raises(KeyError):
        executor.history.restore(0, ["nowhere.at.all"])


def test_persisted(executor, platform, tmp_path):
    executor(fake(npoints=3)).update()
    executor.platform_state[DRIVE1] = 4.5e9
    lines = (tmp_path / "s" / FILE).read_text().splitlines()
    assert len(lines) == len(executor.history) == 3
    attached = Executor(platform, session=Session.attach(tmp_path / "s"))
    assert attached.history.entries == executor.history.entries
    attached.platform_state[DRIVE0] = 4.4e9
    assert attached.history[-1].parent == 2
    assert [e.kind for e in attached.history] == ["start", "update", "edit", "edit"]


def test_written_once_started(platform, tmp_path):
    executor = Executor(platform, path=tmp_path / "s", targets=TARGETS)
    executor.platform_state[DRIVE0] = 4.1e9  # before the session folder exists
    assert not (tmp_path / "s").exists()
    executor(fake(npoints=3))
    assert len((tmp_path / "s" / FILE).read_text().splitlines()) == len(
        executor.history
    )


def test_new_session(executor, tmp_path):
    executor.platform_state[DRIVE0] = 4.1e9
    executor.new_session(tmp_path / "t")
    assert len(executor.history) == 0


def test_reused_update_applied(platform, tmp_path):
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=100,
        delay_between_pulses_step=30,
    )
    executor = Executor(platform, path=tmp_path / "s", targets=TARGETS, update=False)
    first = executor.submit(bound, reuse=True).result(10)
    first.update([1])
    reused = executor.submit(bound, reuse=True)
    assert reused.status == "done" and reused().path == first.path
    assert reused().updates.pending == [0]  # 1 was applied


def test_log(executor):
    executor.platform_state[DRIVE0] = 4.1e9
    log = executor.history.log()
    assert list(log["change"]) == ["start", "edit"]


def test_additions_and_removals():
    before = {"parameters": {"a": 1, "b": {"c": 2}}}
    after = {"parameters": {"a": 1, "b": {"d": None}, "e": [1, 2]}}
    changes = _changes(before, after)
    assert changes == [
        {"path": "parameters.b.c", "old": 2},
        {"path": "parameters.b.d", "new": None},
        {"path": "parameters.e", "new": [1, 2]},
    ]
    replayed = json.loads(json.dumps(before))
    for change in changes:
        if "new" in change:
            _put(replayed, change["path"], change["new"])
        else:
            _remove(replayed, change["path"])
    assert replayed == after


# -- explorer -----------------------------------------------------------------------


def test_explorer(executor):
    pytest.importorskip("anywidget")
    executor.platform_state[DRIVE0] = 4.1e9
    executor.platform_state[DRIVE1] = 4.25e9
    explorer = executor.history.explore()
    assert [e["id"] for e in explorer.entries] == [2, 1, 0]  # newest first
    assert explorer.entries[0]["head"]
    assert (explorer.a, explorer.b) == (1, 2)  # the latest change
    assert [row["path"] for row in explorer.diff] == [DRIVE1]
    assert explorer.diff[0]["b"] == "4.25 GHz"

    explorer._message(explorer, {"kind": "select", "a": 0, "b": 2}, [])
    assert {row["path"] for row in explorer.diff} == {DRIVE0, DRIVE1}

    explorer._message(explorer, {"kind": "restore", "paths": [DRIVE1]}, [])
    assert explorer.snippet == f'executor.history.restore(0, ["{DRIVE1}"])'
    assert executor.history[-1].paths == [DRIVE1]
    assert explorer.b == 3 and explorer.entries[0]["head"]

    explorer._message(explorer, {"kind": "restore", "paths": None}, [])
    assert explorer.snippet == "executor.history.restore(0)"
    other = [e for e in explorer.entries if not e["lineage"]]
    assert {e["id"] for e in other} == {1, 2, 3}  # another branch now

    explorer._message(explorer, {"kind": "restore", "paths": ["nowhere"]}, [])
    assert explorer.error.startswith("KeyError")


def test_explorer_empty(executor):
    pytest.importorskip("anywidget")
    explorer = executor.history.explore()
    assert explorer.entries == [] and "No platform change" in explorer.error
