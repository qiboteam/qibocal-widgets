# Remote execution

Status: implemented (first version), with follow-ups below. Tracks
[#1](https://github.com/qiboteam/qibocal-widgets/issues/1), following
[qiboteam/qibocal#1210](https://github.com/qiboteam/qibocal/issues/1210).
User documentation: `docs/source/getting-started/remote.rst`.

## Decisions

- **A runner, not an executor subclass**: `Remote` fills the single `runner`
  role of the general-purpose `Executor`, next to its frontends and
  middleware, instead of multiplying classes (see
  [architecture.md](architecture.md)).
- **Cut at the executor level**: on the remote side, a plain
  `qibocal.Executor` runs the step, the most tested path of Qibocal.
- **Multi-tier, as in the interactive architecture of Qibocal and in
  qibocal-report**: nothing on the compute node, one blocking `srun` job per
  step from the access node, optionally through SSH from a laptop. The tier
  follows from the connection options, not from detection.
- **No Dask**: too specific; plain `srun` covers the queue. `submitit` remains
  an option if ever needed.
- **JSON and NPZ only, no pickle**: protocols by `module:attribute`
  reference, parameters as JSON documents, platform state as Qibocal's JSON
  dumps, data and results as the files of their `save` methods.
- **Further protocols through environment management**, as qibocal-report
  does for notebooks: requirements in `requirements.txt` format, installed
  separately (`Remote.install()`) from execution.
- **Connections configurable on the runner or by name**, in a file shared with
  qibocal-report, to be editable from its launcher
  ([qibocal-report#53](https://github.com/qiboteam/qibocal-report/issues/53)).

## How it works

### Steps

| Step | Where | Why |
| --- | --- | --- |
| `acquire` | remote (through the queue, if configured) | needs the instruments |
| `fit`, `report` | local | pure functions of data and results |
| `update` | local with a local platform, else remote on the access node | only modifies parameters |
| `open`, `close` | skipped when dispatching | the platform is connected by each job |

Checked on `protodev`: none of the 73 `fit` and 67 `report` callbacks of the
built-in protocols takes the platform.

### Platform state

Jobs are independent: each one recreates the platform by name, then applies
the current `parameters` and `calibration` JSON. The state comes from the
local platform when the executor has one (updates are applied to it locally),
otherwise from the state returned by the last remote update, kept by the
runner. Verified: a changed drive frequency reaches a freshly created
platform, which still connects.

### Wire protocol

Aligned with qibocal-report:

- commands are plain `ssh` and `srun` subprocesses; SSH runs with
  `-T -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3`;
  `srun --unbuffered [--partition Q] [options] --nodes=1 --ntasks=1`;
- the worker source is shipped inline (`python3 -u -c`), so the remote
  machine only needs Qibocal in the environment;
- the job is written as JSON on the worker's standard input, and the outcome
  read from a `QIBOCAL_WIDGETS_RESULT {json}` line on its standard output,
  with files base64-encoded;
- the bootstrap runs on the system `python3` (standard library only), and
  re-runs the job with the environment's interpreter.

### Configuration

`remotes.json`, next to qibocal-report's files
(`$QIBOCAL_REPORT_CONFIG_DIR`, `$XDG_CONFIG_HOME/qibocal`,
`~/.config/qibocal`), versioned and written atomically like them:

```json
{"version": 1, "connections": {"lab": {"ssh": "me@login", "queue": "qpu"}}}
```

Fields: `ssh`, `queue`, `slurm`, `workdir`, `venv`, `requirements`,
`rebuild_on_compute` (same meaning as qibocal-report's notebook connections),
plus `python` (interpreter or uv version for the environment), `platform`, and
`timeout`. `QIBOCAL_WIDGETS_CONNECTION` selects a named connection for
`Remote()`, so notebooks need no change across tiers.

### Environments

Same location (`~/.cache/qibocal/envs/<venv>`), installer (uv, else venv and
pip; `QIBOCAL_NO_UV`), and requirements marker file as qibocal-report, so an
environment prepared by one tool is recognized by the other.

## Testing

Fake `ssh`, `srun`, `python3` and `uv` executables on `PATH` log their
arguments and run the actual commands locally, so the full exchange runs for
real, against Qibocal's mock platform (vendored in `tests/platforms`): both a
fake protocol (importable by reference from `tests/fake.py`) and the built-in
`ramsey_signal`, with state round-trips through remote and local updates,
timeouts, unreachable hosts, missing environments, and unavailable protocols.

## Follow-ups

1. **Launcher integration** (qibocal-report#53): a "Remote execution" section
   editing `remotes.json`; the schema is meant to be shared, possibly moving
   the connection model to a common package.
2. **Report server on the same channel** (as qibocal-report#50 does for
   notebooks): persist remote outputs in the executor's output folder, so a
   report server can serve them.
3. **Persisting outputs**: today data are loaded into memory; dumping them
   (and the platform state) in the executor's `path` would mirror local runs.
4. **Cancellation**: interrupting the kernel kills the local `ssh`/`srun`
   process; check that the remote job is reliably cancelled (process groups,
   or `scancel` by job name).
5. **Connection reuse**: one SSH connection per step; `ControlMaster`
   multiplexing would cut the latency of repeated steps.
6. **Long queues**: a blocking `srun` keeps the notebook busy while queued.
   An asynchronous mode (submitted job, future-like execution displayed as
   pending, then completed) would pair with the
   [SLURM monitor](slurm-monitor.md).
7. **Remote platform inspection**: a `describe` action returning the current
   remote platform parameters, for display without a local platform.
8. **Coverage of the worker**: it runs in subprocesses, so its coverage is not
   measured; enable subprocess coverage collection.
