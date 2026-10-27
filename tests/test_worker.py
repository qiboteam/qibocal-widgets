"""The remote worker, executed in-process.

The end-to-end tests run the worker as remote machines do (inline source, in
subprocesses), where coverage cannot follow it. These tests call its actions
directly, so that they are measured.
"""

import base64
import io
import json
import sys
from pathlib import Path

import pytest
from conftest import PLATFORMS, TARGETS
from fake import FakeResults, fake

from qibocal_widgets._core.remote import jobs, worker


@pytest.fixture(autouse=True)
def mock(monkeypatch):
    monkeypatch.setenv("QIBOLAB_PLATFORMS", str(PLATFORMS))


def acquire_job(**extra):
    return {
        **jobs.acquire_job(
            fake(npoints=4),
            platform="mock",
            targets=TARGETS,
            state=None,
            overrides={"nshots": 32},
        ),
        **extra,
    }


def test_acquire():
    outcome = worker.acquire(acquire_job())
    assert set(outcome["files"]) == {"data.json", "data.npz"}
    assert outcome["targets"] == TARGETS
    assert outcome["parameters"]["nshots"] == 32
    data = jobs.load_files(outcome["files"], fake.data_type.load)
    assert sorted(data.qubits) == TARGETS


def test_state_and_describe():
    described = worker.describe({"platform": "mock"})["state"]
    parameters = json.loads(described["parameters"])
    drive = "0/drive"
    parameters["configs"][drive]["frequency"] = 4.5e9
    state = {**described, "parameters": json.dumps(parameters)}
    outcome = worker.acquire(acquire_job(state=state))
    data = jobs.load_files(outcome["files"], fake.data_type.load)
    assert data.scale[0] == 4.5e9


def test_update():
    results = FakeResults(peak={0: 1.25})
    job = jobs.update_job(
        fake(npoints=4), results, platform="mock", targets=[0], state=None
    )
    state = worker.update(job)["state"]
    assert json.loads(state["parameters"])["configs"]["0/drive"]["frequency"] == 1.25e9


def test_bind_plain_parameters():
    from qibocal import protocols

    reference = "qibocal.protocols:ramsey_signal"
    bound = worker.bind(
        {
            "protocol": reference,
            "parameters": {
                "delay_between_pulses_start": 10,
                "delay_between_pulses_end": 50,
                "delay_between_pulses_step": 20,
            },
        }
    )
    assert bound.protocol == protocols.ramsey_signal


def test_files_roundtrip(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.npz").write_bytes(b"\x00\x01")
    encoded = worker.encode(tmp_path)
    assert base64.b64decode(encoded["b.npz"]) == b"\x00\x01"
    target = tmp_path / "out"
    target.mkdir()
    worker.decode(encoded, target)
    assert (target / "b.npz").read_bytes() == b"\x00\x01"


def test_environment_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert worker.environment_path("qibocal") == tmp_path / "qibocamp/envs/qibocal"
    assert worker.environment_path("/opt/env") == Path("/opt/env")
    assert worker.environment_path("~/env") == Path.home() / "env"


def run_main(monkeypatch, capsys, job, guard=True):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(job)))
    if guard:
        monkeypatch.setenv(worker.GUARD, "1")
    else:
        monkeypatch.delenv(worker.GUARD, raising=False)
    code = worker.main()
    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(worker.MARKER)
    ]
    return code, json.loads(lines[-1][len(worker.MARKER) :])


def test_main(monkeypatch, capsys):
    code, outcome = run_main(
        monkeypatch, capsys, {"action": "describe", "platform": "mock"}
    )
    assert code == 0 and outcome["ok"]
    assert "parameters" in outcome["state"]


def test_main_failure(monkeypatch, capsys):
    code, outcome = run_main(
        monkeypatch, capsys, {"action": "describe", "platform": "nowhere"}
    )
    assert code == 1 and not outcome["ok"]
    assert "Traceback" in outcome["traceback"]


def test_main_missing_environment(monkeypatch, capsys, tmp_path):
    job = {"action": "describe", "platform": "mock", "venv": str(tmp_path / "no")}
    code, outcome = run_main(monkeypatch, capsys, job, guard=False)
    assert code == 1
    assert "Environment not found" in outcome["error"]


def test_main_install(monkeypatch, capsys, tmp_path):
    env = tmp_path / "env"

    def installer(command):
        env.mkdir(exist_ok=True)

    monkeypatch.setattr(worker, "run_installer", installer)
    monkeypatch.setenv("QIBOCAMP_NO_UV", "1")
    code, outcome = run_main(
        monkeypatch, capsys, {"action": "install", "venv": str(env)}, guard=False
    )
    assert code == 0 and outcome["installed"]


def test_jsonable():
    import numpy as np

    assert worker.parameters_document({"a": np.arange(2), "b": (1, 2)}) == {
        "a": [0, 1],
        "b": [1, 2],
    }
    with pytest.raises(TypeError):
        worker.parameters_document({"a": object()})


def test_main_platforms_dir(monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(PLATFORMS.parent))
    monkeypatch.delenv("QIBOLAB_PLATFORMS")
    code, outcome = run_main(
        monkeypatch,
        capsys,
        {"action": "describe", "platform": "mock", "platforms_dir": "~/platforms"},
    )
    assert code == 0 and outcome["ok"]
    import os

    assert os.environ["QIBOLAB_PLATFORMS"] == str(PLATFORMS)
