# Architecture

Status: implemented.

## Goal

In a notebook, the result of any executor phase should display itself, with
no helper call:

```python
with executor:
    acquired = executor.acquire(bound, targets=[0, 1])
acquired  # raw data tables

reported = executor.report(executor.fit(acquired))
reported  # raw data + per-target reports
```

## How it works

All the implementation lives in the private `qibocal_widgets._core`
subpackage; the public modules (`qibocal_widgets`, `qibocal_widgets.marimo`,
`qibocal_widgets.jupyter`, `qibocal_widgets.remote`,
`qibocal_widgets.explorer`, `qibocal_widgets.monitor`) only re-export from it, which a test enforces.
Frontends are kept as thin as possible, on top of frontend-agnostic
extraction.

### 1. Extraction (`_core.data`, `_core.reports`)

Pure data manipulation, no frontend import.

- `data_frames(data) -> dict[target, DataFrame]`: one table per target.
  Record arrays become one column per field; complex arrays become
  `real/imag/signal/phase`; per-target sequences stored on the data object
  outside the records (e.g. `drive_frequencies` of spectroscopies) are attached
  as extra columns when their length matches. This generalises the special
  case hard-coded for `QubitSpectroscopyData` in the original helper, without
  importing any protocol.
- `reports_of(reports) -> dict[target, Report]`: normalises whatever a report
  callback returned (per-target `(figures, table)` tuples, a single figure, a
  list of figures, bare HTML) into a `Report(figures, table, extra)` object.

### 2. Executor roles (`_core.executor`, `_core.runner`, `_core.middleware`, `_core.frontend`)

`Executor(qibocal.Executor)` is composed of three roles, each matching a class
of extensions with different semantics:

| Role | Cardinality | Order | Extensions |
| --- | --- | --- | --- |
| `runner` (`Runner`) | exactly one, default `Local` | innermost | remote/SLURM, async jobs, `submitit`, cancellation |
| `middleware` (`Middleware`) | any | registration order, first outermost | timing, logging, caching, persistence, progress, history, background execution |
| `frontends` (`Frontend`) | any | irrelevant | Marimo, Jupyter, HTML fallback, further tabs and renderers |

- The **runner** does the actual work of every step. The base `Runner` calls
  Qibocal's implementation for the protocol steps, and only connects and
  disconnects the platform on `open`/`close` (reached by both `with
  executor:` and the `Executor.open(...)` classmethod): the output folder
  belongs to the session (section 5). A runner executing some steps elsewhere
  overrides only those. Being a single slot, it needs no conflict resolution,
  and runner-specific operations (`Remote.install()`, `Remote.describe()`,
  `Remote.queue()`, `Remote.monitor()`) have a natural home. Runners also own the platform state the steps run on
  (`platform_state`, `set_platform_state`), which sessions and
  `executor.platform_state` go through.
- **Middleware** hooks, one per step, receive the executor and the next
  callable, like web-server middleware: they can alter arguments,
  post-process the output, or not call the next callable. The runner is always
  the innermost layer, so every middleware sees every step regardless of
  order. A `result` hook transforms the output of every step.
- **Frontends** render executions for one display protocol. The executor
  attaches all of them to every output, after the middleware result hooks;
  `wrap(completed)` does the same without an executor. Frontends whose views
  interact with the executor (e.g. a phase-control toolbar) receive it in
  `attach`.

`Executor.__call__` is inherited: it calls the overridden phases, so the full
workflow goes through all the roles with no dedicated hook. Objects given in
the wrong role are rejected with a `TypeError`.

Every output is converted (`convert`) to `qibocal_widgets.Completed`
(`_core.completed`), a subclass of Qibocal's `Completed` with a `views` field:
displayable views keyed by display protocol (`_display_` for Marimo,
`_repr_mimebundle_` for Jupyter). Missing views fall back to the plain
representation, so several frontends coexist on the same object. Conversion is
idempotent and does not trigger lazy loading of data stored on disk; Qibocal's
downstream phases use `dataclasses.replace`, which preserves the subclass and
its views.

All the constructors of `Executor` (`create`, `open`, the default one) are
inherited, and forward the role arguments.

### 3. Frontends (`_core.marimo`, `_core.jupyter`)

Titles and initial states are a shared policy in `_core.layout`: the
*Reports* tab is selected when available, per-target accordions start
expanded only for a single target, and the fit results table is placed above
the plots, centered, in a nested section folded by default.

Each defines:

- `show_data(data | completed)` and `show_reports(reports | completed)`: the
  explicit helpers (accordion per target; folded fit table above the
  figures).
- `display(completed)`: data and reports in tabs, plus an error section when
  the execution failed. Sections that are not available are omitted.
- the `Marimo` / `Jupyter` frontend, rendering with `display` for its display
  protocol.
- `wrap(completed)`: the same, on a single execution.

Marimo renders with `mo.ui.table`, `mo.ui.plotly`, `mo.Html`, `mo.accordion`,
`mo.ui.tabs`. Jupyter renders with `ipywidgets` containers (`Accordion`,
`Tab`, `Output`) and lets pandas and Plotly use their native Jupyter renderers
inside the output widgets.

### 4. Output location (`_core.output`)

Following [#2](https://github.com/qiboteam/qibocal-widgets/issues/2), the
session's reports folder (`QIBOCAL_REPORTS_DIR`, exported by qibocal-report's
notebook sessions) is the default parent of the output path of
`Executor.create` and `Executor.open`: each executor writes to a fresh
`<YYYY-MM-DD>_<HH-MM-SS>_<user>` subfolder (UTC, numeric suffix on
collisions), recognized by the report server through its `meta.json`. An
explicit `path` keeps its meaning; without either, `create` raises a
`TypeError`. The default constructor is unchanged: without `create`, there is
no metadata, hence no output. `reports_dir()` exposes the folder.

### 5. Sessions (`_core.session`)

Following [#4](https://github.com/qiboteam/qibocal-widgets/issues/4), an
executor with an output path owns a `Session`, recording every execution in
its folder, appended for as long as the instance lives. Qibocal's own folder
management is bypassed on purpose, to keep Qibocal simple: its `_init` refuses
existing folders, and its `close` rewrites `history.json` from the executions
of the current instance only, so it cannot append. The runner's `open`/`close`
only connect and disconnect the platform.

- The folder keeps the layout of runcard outputs (`data/<id>-<iteration>/`
  with `action.yml`, data and results files; `history.json`; `meta.json`;
  `platform/` and `new_platform/`), so `Output.load`, `Completed.load`, and
  qibocal-report read it unchanged. The id is the registered protocol name.
- Every change is written immediately: notebooks rarely close their
  executor.
- Acquisitions create task folders; fits write results in the folder of the
  acquisition (overwriting when re-fitting); executions from elsewhere are
  recorded as new tasks; updates dump the platform.
- The folder is created at the first context entry or recording, so remote
  executions, which never enter the context, are recorded too.
- Protocols not registered in `qibocal.protocols` are recorded in `data/`,
  but kept out of `history.json`: Qibocal cannot load them, and listing them
  would break loading the whole folder.
- `new_session()` switches to a new folder; `Executor.attach(path)` (or an
  explicit `Session.attach`) continues an existing one, restoring the latest
  recorded platform state.
- Platform states are obtained from, and restored through, the runner
  (`Runner.platform_state`, `Runner.set_platform_state`): a remote runner
  without a local platform records the state it keeps (`Remote.state`, asked
  to the remote machine at the start) after updates, and gets it back when
  attaching.
- Notes (`executor.note`, `Session.note`) go to Qibocal's `notes.json`, in the
  session folder or in an execution folder, written with the lock and atomic
  replacement used by qibocal-report's server, which may add notes
  concurrently.
- Protocols are identified by equality, not identity: loaded executions hold
  copies of their protocol.

### 6. Platform states (`_core.state`, `_core.explorer`)

Following [#3](https://github.com/qiboteam/qibocal-widgets/issues/3),
`PlatformState` explores and updates the calibration state of a platform by
path, from code and with an interactive explorer.

- It works on the JSON documents of the state (`parameters`, `calibration`),
  not on platform objects, so the same API covers a local platform, the state
  kept by a remote runner (asked to the remote machine through a `describe`
  job when unknown), session folders, and snapshots.
- Paths are dotted over the JSON documents, rooted at the document name.
  Within a document, they coincide with qibolab's `Platform.update` paths and
  with the dashboard's (checked: qibolab accepts the JSON form, pair keys
  included). Pasted text is resolved leniently: root-less paths, and paths
  quoted in code or output.
- Updates are atomic and validated against the qibolab and Qibocal models,
  and require existing paths. Through `executor.platform_state`, they go
  through the runner (`Runner.set_platform_state`) and are recorded in the
  session, as protocol updates.
- The explorer is a single [anywidget](https://anywidget.dev), displayed
  natively by Jupyter and Marimo: the only way to get clipboard access and a
  real navigation bar in both, with one implementation. All the logic
  (resolution, search, formatting, comparison, edits) is in Python, and
  tested there; the browser side is a plain ES module (no build step) which
  renders rows and sends requests back.

## Alternatives considered

### One executor subclass per feature, combined by inheritance

The first implementation shipped `MarimoExecutor` and `JupyterExecutor`, and
the remote execution proposal combined features through cooperative
subclasses (`class MarimoRemoteExecutor(MarimoExecutor, RemoteExecutor)`).
Rejected: every new feature multiplies the classes to provide, while roles
compose freely.

### A single list of plugins (or middleware)

The second implementation registered everything in one `plugins=[...]` list,
with middleware-like hooks, and exclusivity groups to reject two plugins
replacing the same step. Replaced by the three roles: dispatching is singular
by nature, so it fits a slot rather than a list with conflict checks; placing
it innermost removes the ordering pitfall of a dispatcher short-circuiting
the plugins after it; and display needs no hooks at all. Plugin also suggested
discovery and global registration, which none of these involve.

### Registering formatters instead of subclassing

Jupyter supports registering a formatter for a type
(`get_ipython().display_formatter.formatters["text/html"].for_type(Completed, ...)`).
That would make every plain `Completed` displayable with no executor wrapper at
all. It was not chosen because:

- Marimo has no public equivalent (its formatter registry is private API and
  keyed on type as well), so the two frontends would diverge.
- A global side effect on import is surprising, and the wrapper approach makes
  the choice of frontend explicit at the point where the executor is created.

It remains possible as an opt-in for Jupyter, but was dropped from the plans,
see [display-features.md](display-features.md).

### A proxy object around the executor (composition)

`Widgets(executor)` forwarding attribute access and wrapping results. Rejected:
`Executor.create`/`open` are classmethods and `with executor:` must keep
working, so a single subclass hosting the roles is both simpler and more
faithful. Composition would also break `isinstance(..., Executor)` checks.

### Monkeypatching `Completed` with display protocol methods

Smallest possible code, but a global patch of a Qibocal class, again with the
frontend chosen implicitly. Rejected for the same reasons as formatters.

### Upstreaming display protocols into Qibocal

`Completed` could grow `_repr_html_` directly in Qibocal, with Plotly figures
serialised to HTML. Plausible long term, but it couples Qibocal to notebook
concerns and to one rendering style; this package is the place to iterate on
that first.

## Known limitations

- `qibocal_widgets.marimo` and `qibocal_widgets.jupyter` import their
  frontend at module import time; the relevant extra must be installed.
- Per-target reports assume the Qibocal convention `(figures, table)`. Other
  shapes are rendered on a best-effort basis (`Report.extra` is shown as text).
- Jupyter rendering relies on `ipywidgets`, and the platform explorer on
  `anywidget`; exported static notebooks (e.g. `nbconvert` without widget
  state) will not show them. A widget-free HTML fallback is discussed in
  [display-features.md](display-features.md).
- Protocols not registered in `qibocal.protocols` are recorded in sessions,
  but neither listed in their history nor shown by qibocal-report, since
  Qibocal can only load registered protocols back.
- The package depends on the unreleased `protodev` branch of Qibocal; see
  [packaging-and-ci.md](packaging-and-ci.md).
