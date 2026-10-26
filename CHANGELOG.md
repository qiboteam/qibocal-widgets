# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

First development version, targeting the executor interface of Qibocal's
`protodev` branch.

### Added

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
- Example notebooks for Marimo and Jupyter, touring all the features on a
  simulated platform, executed in the documentation.
