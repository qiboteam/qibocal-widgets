# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

First development version, targeting the executor interface of Qibocal's
`protodev` branch.

### Added

- `Executor.submit`: background executions, returning a `Pending` execution
  (`pending()` to peek, blocking `result()`, or `await`), queued together with
  remote runners and processed in submission order; displayed live in
  Jupyter; in Marimo, run in `mo.Thread` and reactive (cells referencing it run
  again when it completes), shown as a spinner replaced by the result.
- Progress of pending executions: their phase (queued, running, receiving the
  data; waiting for earlier executions, fitting, reporting, updating), and
  bars for the current `platform.execute()` call and its batch, from the
  estimates logged by qibolab and its drivers (e.g. Qblox), captured locally
  or streamed back by remote workers, with the estimates and measured times
  of all of them (`Pending.timeline`, `Pending.phase`). The view updates in
  place, with fixed-width numbers, so that only values change.
- Remote agents: a warm worker per runner, started once over a single SSH
  connection, outside of the queue, serving every step (updates, states,
  layouts, saves at once; acquisitions through the queue as `srun` jobs, or,
  without a queue, in the agent itself); it exits with the notebook. The
  queue is never held between acquisitions (`agent=False` for a process per
  step).
- Detached remote jobs: queued acquisitions survive disconnections and
  restarts of the kernel; recorded in the session until fetched, they are
  followed again by `submit(..., reuse=True)`, still running or done
  meanwhile, instead of acquiring again.
- `pending.started_at`: when an execution started, once confirmed with
  `confirm`; times, totals and profiles count from there, not from the
  submission.
- Cancelling executions: `pending.cancel()`, and a *Cancel* button on their
  progress, ending them as `cancelled` (`Cancelled`): queued remote jobs are
  stopped (`SIGTERM`, then `SIGKILL`), in-process acquisitions stop before
  their next execution on the platform, executions not started never start;
  interrupting the kernel stops the remote job of a blocking call.
- `platform_updates`: values set by path for one execution only, as the
  `updates` of `platform.execute`, for `submit`, `acquire` and blocking
  calls, locally and remotely; the platform state and its history are not
  changed; part of the reuse key, and recorded with the execution.
- Profiles in the displayed executions: a *⏱ profile* toggle by the timing,
  with the steps, and buttons copying them as Markdown or CSV, with the
  context (setup, agent, versions; no host names). Blocking calls are
  profiled too (`completed.profile()`, `completed.profile_report()`), and the
  start of the remote agent is a step of its own.
- `pending.profile()`: where the time of an execution went, step by step:
  remote jobs report their stages (out of the queue, imports, platform
  creation, connection, disconnection, encoding), also shown as phases while
  running, and the executor its own (transfer, recording, fitting,
  reporting). Remote environments are installed with compiled bytecode.
- Executions show a header line: the protocol, how long the acquisition and
  the fit took (and the total, since submitted, for background executions),
  and, on the right, the *Run again* and *Update* buttons; each target's
  *Update* is on the line of its fit results.
- `executor.describe_platform()`: qubits, couplers, channels (kind, port, LO,
  mixer), and instruments of the platform, also for remote runners without a
  local platform; `PlatformLayout.lo_config` locates the LO of a channel in
  the platform state, and `sharing` the channels using it.
- `executor.history`: the platform states of the session, as diffs, with
  their origin (updates, edits, restores, external changes); compared,
  restored entirely (forking the history) or for some paths, recorded in the
  session folder, and explored interactively (`history.explore()`).
- `PlatformState.save()`: the state written back to the platform folder (on
  the remote machine, for remote runners without a local platform), or to any
  folder, formatted as qibolab dumps it; files are replaced in git working
  trees, or with `overwrite=True`.
- Approving platform updates after validating the fit, with `update=False`:
  `completed.update()` and `pending.update()`, for all targets or some, and
  *Update* buttons (all targets, and per target in each report), showing when
  applied.
- `confirm`: executions wait for confirmation, displayed as a *Run* button
  (`pending.start()` from code), so that notebooks start nothing by
  themselves; only where a frontend can show it, at once elsewhere.
- *Run again* button on completed executions (`pending.rerun()`), whatever
  `reuse`: the same handle follows the new execution, recorded anew.
- `Executor(confirm=..., reuse=...)`: defaults of `submit`'s arguments, both
  off by default.
- `submit(..., reuse=True)`: an identical execution, running or recorded in
  the session, is returned instead of acquiring again (same protocol,
  parameters, overrides, and targets, whatever the platform state).
- `platforms_dir` in remote connections: the platforms folder on the remote
  machine, replacing its `QIBOLAB_PLATFORMS`, so that a stored connection
  needs no environment variable there.
- A named remote connection has an environment of its own by default,
  `_remote/<name>`, as Qibocamp's desktop application resolves it.
- `Executor`, a drop-in replacement of `qibocal.Executor`, composed of a
  runner, middleware, and frontends.
- `Marimo` and `Jupyter` frontends, displaying executions with no helper call
  (raw data, per-target reports, folded fit tables), with explicit
  `show_data`, `show_reports`, and `wrap` helpers.
- Remote execution (`qibocal_widgets.remote.Remote`): acquisitions dispatched
  through SLURM and SSH, with JSON and NPZ jobs, named connections shared with
  Qibocamp, and separately installed environments.
- Session folders: every execution recorded and appended in Qibocal's output
  layout, readable by Qibocal and Qibocamp; `new_session()`,
  `Executor.attach()`, platform states, and notes.
- Default output location from the session's reports folder
  (`QIBOCAMP_REPORTS_DIR`), and `reports_dir()`.
- `PlatformState`: platform parameters and calibration by path, with an
  interactive explorer for Jupyter and Marimo.
- `Remote.queue()` and `Remote.monitor()`: the SLURM queue of the connection,
  with Qibocamp's query, and a refreshable view highlighting the user's
  jobs and the runner's (named `qibocal-widgets-<action>`).
- Example notebooks for Marimo and Jupyter: `calibration`, touring the
  features on a simulated platform, executed in the documentation, and
  `remote`, running acquisitions on a cluster.
