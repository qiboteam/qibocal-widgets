# Richer display of executions

Status: proposals. Extends what frontends show, keeping the "no explicit
invocation" principle. New renderings belong to the frontends (`Marimo`,
`Jupyter`), on top of frontend-agnostic extraction in the core, as the current
data and report views.

## Done

- **Display without helpers**, for Marimo and Jupyter, coexisting on the same
  execution (see [architecture.md](architecture.md)).
- **Reports first**: the *Reports* tab is selected when available, single
  targets start expanded, and the fit table is folded above the plots.
- **Loading from disk**: `Executor.load(path)` returns a displayable execution,
  and `Executor.attach(path)` continues a session folder.

## Remaining

### 1. Results section

`Completed.results` is left to the frontend's default representation; the
fitted values only appear in the protocol's report table. Qibocal `Results`
are dataclasses whose fields are mostly `dict[target, value]` (scalars,
`(value, error)` pairs, or small arrays).

- Core: `results_frame(results) -> DataFrame`, one row per target and one
  column per field, flattening `(value, error)` into two columns.
- Frontends: a *Results* tab between *Data* and *Reports*, omitted when the fit
  did not run.

### 2. Execution summary and parameters

A compact header above the tabs: protocol name, targets, acquisition and fit
durations (`data_time`, `results_time`), success, and the session task id when
recorded (`data/<id>-<iteration>`). The executed parameters (`bound.parameters`,
including `nshots` and `relaxation_time`), folded by default, make each cell
output a complete record of the experiment.

### 3. Session browser

The session folder is the natural history of a notebook: displaying
`executor.session` (or any `Session.attach(path)`) lists the recorded tasks
(`history.json`, timings from `meta.json`, notes), and expands each into the
full display of its execution, loaded lazily with `Completed.load`. This also
makes widgets usable for post-processing, with no platform at all. Replaces
the earlier idea of a browser over `Executor.history`, which sessions
superseded.

### 4. Widget-free HTML fallback (Jupyter)

The `Jupyter` frontend needs `ipywidgets`, so static exports (`nbconvert`,
GitHub rendering, Sphinx `nbsphinx`) lose the content. A view returning a
`text/html` bundle (pandas `to_html`, Plotly `to_html(full_html=False,
include_plotlyjs="cdn")`, `<details>` elements as accordions) would keep it;
a `Jupyter(widgets=False)` option picks the renderer.

### 5. Comparison of executions

Overlay the figures of two executions of the same protocol (e.g. before and
after an update) on the same axes, per target. A first version can stack them
side by side; sessions provide the natural pairs (iterations of the same task
id).

### 6. Custom renderers per data type

Let protocols (or users) register a `(DataType) -> DataFrame` or
`(Completed) -> displayable` override, for data layouts the generic tabulation
handles poorly (2-D sweeps, randomized benchmarking sequences): a dictionary in
the core, keyed by class, consulted by the extraction functions.

## Dropped

- **Opt-in formatter registration for plain `qibocal.Completed`** (Jupyter
  only): the executor and `wrap(completed)` already make any execution
  displayable, in both frontends, without a global side effect; a
  Jupyter-only path would split the two frontends for little gain.
- **A separate `qibocal_widgets.load(path, frontend=...)`**: covered by
  `Executor.load` and `Executor.attach`, and by the session browser above.
