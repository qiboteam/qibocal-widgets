"""The SLURM queue, against fake ``squeue``, ``sinfo``, ``whoami`` and ``ssh``."""

import json
import os
import stat
import sys

import pytest

from qibocal_widgets._core.remote import queue
from qibocal_widgets.remote import Connection, Remote

SQUEUE = """\
101|qpu|qibocal-widgets-acquire|alice|RUNNING|0:42|10:00|1|node1|1000|2026-10-21T10:00:00|2026-10-21T10:00:05
102|qpu|qibocal-widgets-acquire|alice|PENDING|0:00|10:00|1|(Resources)|990|2026-10-21T10:01:00|N/A
103|qpu|other-job|bob|PENDING|0:00|1:00:00|1|(Priority)|980|2026-10-21T10:02:00|N/A
broken line
"""
SINFO = """\
qpu*|up|1|alloc
qpu*|up|2|idle
"""


def executable(path, body):
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def slurm(tmp_path, monkeypatch):
    """Fake SLURM commands, logging their arguments."""
    if sys.platform == "win32":
        pytest.skip("the fake SLURM tools are POSIX executables")
    bin = tmp_path / "bin"
    bin.mkdir()
    log = tmp_path / "log.jsonl"
    record = (
        "import json, os, sys\n"
        "with open(os.environ['FAKE_LOG'], 'a') as log:\n"
        "    log.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]]) + '\\n')\n"
    )
    executable(bin / "squeue", record + f"sys.stdout.write({SQUEUE!r})\n")
    executable(bin / "sinfo", record + f"sys.stdout.write({SINFO!r})\n")
    executable(bin / "whoami", "print('alice')\n")
    executable(
        bin / "ssh",
        record + "os.execvp('sh', ['sh', '-c', sys.argv[-1]])\n",
    )
    monkeypatch.setenv("PATH", f"{bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return calls


def test_same_query_as_qibocal_report():
    """Pinned to qibocal_report.remote.slurm, so that both tools agree."""
    assert queue.SQUEUE_FORMAT == "%i|%P|%j|%u|%T|%M|%l|%D|%R|%Q|%V|%S"
    assert queue.SINFO_FORMAT == "%P|%a|%D|%T"
    assert queue.SEPARATOR == "---QIBOCAL-QUEUE---"
    assert queue.shell_script("qpu", "alice", ["PENDING"]) == (
        "squeue -h -o '%i|%P|%j|%u|%T|%M|%l|%D|%R|%Q|%V|%S' --sort=-p,i -p qpu "
        "-u alice -t PENDING; printf '\\n---QIBOCAL-QUEUE---\\n'; "
        "sinfo -h -o '%P|%a|%D|%T' -p qpu; printf '\\n---QIBOCAL-QUEUE---\\n'; whoami"
    )


def test_parse():
    running, pending, other = queue.parse_squeue(SQUEUE)
    assert running["nodes"] == "node1" and running["reason"] == ""
    assert pending["reason"] == "Resources" and pending["nodes"] == ""
    assert pending["start"] == ""
    assert other["time_limit"] == "1:00:00"
    nodes = queue.parse_sinfo(SINFO)
    assert nodes[0] == {
        "partition": "qpu",
        "default": True,
        "available": "up",
        "nodes": 1,
        "state": "alloc",
    }
    summary = queue.summarize([running, pending, other], nodes)
    assert summary["jobs"] == {"RUNNING": 1, "PENDING": 2}
    assert summary["nodes"] == {"ALLOC": 1, "IDLE": 2}
    assert summary["available"] is True


def test_query_local(slurm):
    answer = Remote(queue="qpu").queue()
    assert answer["error"] is None
    assert answer["partition"] == "qpu"
    assert answer["user"] == "alice"
    assert [job["id"] for job in answer["jobs"]] == ["101", "102", "103"]
    assert [job["mine"] for job in answer["jobs"]] == [True, True, False]
    assert [job["ours"] for job in answer["jobs"]] == [True, True, False]
    squeue_call = next(call for call in slurm() if call[0] == "squeue")
    assert squeue_call[-2:] == ["-p", "qpu"]


def test_query_ssh(slurm):
    answer = Remote(ssh="-J bastion me@login", queue="qpu").queue(states=["PENDING"])
    assert answer["error"] is None
    calls = slurm()
    ssh = calls[0]
    assert ssh[0] == "ssh" and ssh[1:3] == ["-J", "bastion"]
    assert "BatchMode=yes" in ssh
    squeue_call = next(call for call in calls if call[0] == "squeue")
    assert squeue_call[-2:] == ["-t", "PENDING"]


def test_query_unavailable(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("POSIX shell")
    monkeypatch.setenv("PATH", str(tmp_path))  # no SLURM, no ssh
    answer = Remote(queue="qpu").queue()
    assert answer["jobs"] == [] and answer["error"]
    unreachable = Remote(ssh="nowhere", queue="qpu").queue()
    assert unreachable["error"]


def test_job_names():
    from qibocal_widgets._core.remote import transport

    named = transport.command(Connection(queue="qpu"), compute=True, action="acquire")
    assert named[named.index("--job-name") + 1] == "qibocal-widgets-acquire"
    custom = transport.command(
        Connection(queue="qpu", slurm="--job-name=mine"), compute=True
    )
    assert "--job-name" not in custom and "--job-name=mine" in custom
    short = transport.command(Connection(queue="qpu", slurm="-J mine"), compute=True)
    assert "--job-name" not in short


def test_monitor(slurm):
    pytest.importorskip("anywidget")
    from qibocal_widgets.monitor import QueueMonitor

    monitor = Remote(queue="qpu").monitor(interval=10)
    assert isinstance(monitor, QueueMonitor)
    assert monitor.interval == 10
    assert monitor.partition == "qpu" and monitor.user == "alice"
    assert monitor.total == 3 and len(monitor.jobs) == 3
    assert monitor.summary["jobs"] == {"RUNNING": 1, "PENDING": 2}
    monitor.mine = True
    assert [job["id"] for job in monitor.jobs] == ["101", "102"]
    asked = len([call for call in slurm() if call[0] == "squeue"])
    monitor._message(monitor, {"kind": "refresh"}, [])
    assert len([call for call in slurm() if call[0] == "squeue"]) == asked + 1
    assert monitor.error == ""


def test_monitor_error(tmp_path, monkeypatch):
    pytest.importorskip("anywidget")
    if sys.platform == "win32":
        pytest.skip("POSIX shell")
    monkeypatch.setenv("PATH", str(tmp_path))
    monitor = Remote(queue="qpu").monitor(interval=0)
    assert monitor.error and monitor.jobs == []
