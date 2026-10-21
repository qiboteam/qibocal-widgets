# SLURM queue monitor

Status: implemented (the remaining part), the rest superseded. The original
idea was a set of widgets to submit, follow, and collect Qibocal jobs on a
SLURM queue from the notebook. Most of it is covered by other pieces; the
queue view is implemented on top of the remote runner.

## Done

- **Queue view in the notebook**: `Remote.queue()` asks the queue once,
  through the runner's connection (over SSH, or locally on the access node),
  and `Remote.monitor()` displays it as a single anywidget, for Jupyter and
  Marimo (`qibocal_widgets.monitor.QueueMonitor`):
  - by default, the whole partition the acquisitions are submitted to, so that
    the jobs ahead are visible;
  - the jobs of the remote user highlighted (`mine`), those of the runner
    tagged (`ours`): its `srun` jobs are now named `qibocal-widgets-<action>`,
    unless the `slurm` options set a name;
  - jobs and nodes by state, pending reasons, time used and limit;
  - refreshed on request, or periodically while displayed (30 s by default,
    configurable from the view); a "mine only" filter.
- **Same query as qibocal-report**: the same `squeue`, `sinfo`, and `whoami`
  round trip and parsed fields (`_core.remote.queue`), with the format strings
  pinned by a test. qibocal-report is a server application, not on PyPI, so
  the query is mirrored rather than imported.

## Remaining

- **Shared package**: move the queue query (and the connection model, see
  [remote-executor.md](remote-executor.md)) to a package common to
  qibocal-widgets and qibocal-report, removing the mirror.
- **Pending executions linked to their jobs**: with asynchronous remote jobs
  (follow-up of [remote-executor.md](remote-executor.md)), pending executions
  could show their job's state, from the same query.

## Superseded

- **Submission and collection of jobs**: the `Remote` runner dispatches each
  step needing the instruments as a blocking `srun` job, optionally through
  SSH, and records its outputs in the executor's session folder (see
  [remote-executor.md](remote-executor.md)). No batch scripts, sidecar files,
  or output conventions are needed.
- **The open questions** of the original proposal are settled there: jobs are
  described in JSON and NPZ (no pickle, no runcards), and SSH goes through
  plain `ssh` with the user's configuration.
- **Platform status widget**: the platform state explorer (#3), with
  comparison against the start of the session.
- **Calibration dashboard**: the report server of qibocal-report serves the
  session folders, and shows the executions and their history.
- **A separate queue backend**: the view reuses qibocal-report's query, as
  above, rather than a new implementation.

## Dropped

- **Instrument health panel** (TWPA pump, temperatures): lab-specific, and
  better served by the labs' own monitoring than by calibration notebooks.
