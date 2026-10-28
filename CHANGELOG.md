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
- Acquisition progress: the duration estimates logged by qibolab and its
  drivers (e.g. Qblox) are captured, locally or streamed back by remote
  workers, and turn the spinner of a pending execution into a progress bar,
  restarting on each refined estimate, with the first one for comparison, and
  the batches done, when the driver estimates them (`Pending.estimates`).
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
