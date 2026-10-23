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
  Qibocamp**: nothing on the compute node, one blocking `srun` job per
  step from the access node, optionally through SSH from a laptop. The tier
  follows from the connection options, not from detection.
- **No Dask**: too specific; plain `srun` covers the queue. `submitit` remains
  an option if ever needed.
- **JSON and NPZ only, no pickle**: protocols by `module:attribute`
  reference, parameters as JSON documents, platform state as Qibocal's JSON
  dumps, data and results as the files of their `save` methods.
- **Further protocols through environment management**, as Qibocamp
  does for notebooks: requirements in `requirements.txt` format, installed
  separately (`Remote.install()`) from execution.
- **Connections configurable on the runner or by name**, in a file shared with
  Qibocamp, to be editable from its launcher
  ([qibocamp#53](https://github.com/qiboteam/qibocamp/issues/53)).

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
otherwise from the state kept by the runner: asked to the remote machine the
first time it is needed (a `describe` job, on the access node, outside of the
queue), then replaced by remote updates and by edits through
`executor.platform_state`. Verified: a changed drive frequency reaches a
freshly created platform, which still connects.

Remote executions, and the platform state before and after updates, are
recorded in the executor's session folder like local ones (see
[architecture.md](architecture.md)); attaching a session hands its latest
state back to the runner.

### Wire protocol

Aligned with Qibocamp:

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

`remotes.json`, next to Qibocamp's files
(`$QIBOCAMP_CONFIG_DIR`, `$XDG_CONFIG_HOME/qibocamp`,
`~/.config/qibocamp`), versioned and written atomically like them:

```json
{"version": 1, "connections": {"lab": {"ssh": "me@login", "queue": "qpu"}}}
```

Fields: `ssh`, `queue`, `slurm`, `workdir`, `venv`, `requirements`,
`rebuild_on_compute` (same meaning as Qibocamp's notebook connections),
plus `python` (interpreter or uv version for the environment), `platform`, and
`timeout`. `QIBOCAL_WIDGETS_CONNECTION` selects a named connection for
`Remote()`, so notebooks need no change across tiers.

### Environments

Same location (`~/.cache/qibocamp/envs/<venv>`), installer (uv, else venv and
pip; `QIBOCAMP_NO_UV`), and requirements marker file as Qibocamp, so an
environment prepared by one tool is recognized by the other.

## Testing

Fake `ssh`, `srun`, `python3` and `uv` executables on `PATH` log their
arguments and run the actual commands locally, so the full exchange runs for
real, against Qibocal's mock platform (vendored in `tests/platforms`): both a
fake protocol (importable by reference from `tests/fake.py`) and the built-in
`ramsey_signal`, with state round-trips through remote and local updates,
timeouts, unreachable hosts, missing environments, and unavailable protocols.

## Follow-ups

### Done

- **Report server and persisted outputs**: remote executions are recorded in
  the executor's session folder (#4), by default under the reports folder
  served by Qibocamp (#2), platform updates included.
- **Remote platform inspection**: the `describe` action returns the remote
  platform state, explored with `executor.platform_state` (#3).
- **Queue**: `Remote.queue()` and `Remote.monitor()` show the SLURM queue of
  the connection, the runner's jobs tagged by name (see
  [slurm-monitor.md](slurm-monitor.md)).

### Remaining

1. **Launcher integration**
   ([qibocamp#53](https://github.com/qiboteam/qibocamp/issues/53)):
   a *Remote execution* section editing `remotes.json`. The connection schema
   is meant to be shared, possibly moving the connection model (and the queue
   query, see [slurm-monitor.md](slurm-monitor.md)) to a package common to
   both.
2. **Cancellation**: interrupting the kernel kills the local `ssh`/`srun`
   process; check that the remote job is reliably cancelled (process groups,
   or `scancel` by job name).
3. **Connection reuse**: one SSH connection per step; `ControlMaster`
   multiplexing would cut the latency of repeated steps.
4. **Long queues**: a blocking `srun` keeps the notebook busy while queued. An
   asynchronous mode (submitted job, pending execution displayed as such, then
   completed and recorded) shares its design with background execution, see
   [interactive-execution.md](interactive-execution.md).
5. **Worker coverage**: see [packaging-and-ci.md](packaging-and-ci.md).
