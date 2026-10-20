# Richer display of executions

Status: proposal. Extends what `display(completed)` shows, keeping the
"no explicit invocation" principle.

## 1. Results section

`Completed.results` is currently left to the frontend's default repr. Qibocal
`Results` are dataclasses whose fields are mostly `dict[target, value]`
(values being scalars, `(value, error)` tuples, or small arrays).

- Core: `results_frame(results) -> DataFrame` with one row per target and one
  column per field, flattening `(value, error)` into `value` / `error`
  columns, and leaving arrays as cell objects (or expanding them into a
  per-target sub-table when 1-D).
- Frontends: a "Results" tab between "Data" and "Reports", hidden when the fit
  phase did not run. `completed.show_results()` as explicit helper.

## 2. Execution summary header

A compact line above the tabs: protocol name (`bound.protocol` function names
or `protocol_id`), targets, acquisition and fit durations (`data_time`,
`results_time`), success flag. Cheap and useful when scrolling through a long
notebook.

## 3. Parameters

Render `bound.parameters` (acquisition), `bound.fitpars`, `bound.reportpars` as
a key/value table, so an execution is self-describing. Combined with the
summary this turns the cell output into a complete record of the experiment.

## 4. Widget-free HTML fallback (Jupyter)

The `Jupyter` plugin currently needs `ipywidgets`. Provide a view returning a
`text/html` bundle (pandas `to_html`, Plotly `to_html(full_html=
False, include_plotlyjs="cdn")`, `<details>` elements as accordion) so that:

- static exports (`nbconvert`, GitHub rendering, Sphinx `nbsphinx`) keep the
  content;
- the `jupyter` extra can drop the hard dependency on `ipywidgets` (kept as
  optional enhancement).

A `Jupyter(widgets=False)` plugin option picks the renderer.

## 5. Opt-in formatter registration (Jupyter)

`qibocal_widgets.jupyter.register()` registering an IPython formatter for the
plain `qibocal.auto.task.Completed`, for users who prefer the stock executor.
See the alternatives discussion in [architecture.md](architecture.md).

## 6. History browser

`Executor.history` collects every execution of a session. A
`show_history(executor)` widget (or making the `Executor` itself
displayable) lists executions with summary rows and expands into the full
display on click. In Marimo this is a `mo.ui.table` with row selection driving
a second cell; in Jupyter a `Select` widget driving an `Output`.

## 7. Comparison of executions

Overlay the figures of two executions of the same protocol (e.g. before and
after an update) on the same axes, per target. Requires a convention for
"same quantity" across figures; a first version can simply stack them side by
side with shared titles.

## 8. Loading reports from disk

`Executor.load(path)` exists; add a `qibocal_widgets.load(path,
frontend=...)` convenience and the ability to browse an output folder
(`Output.load`) as a history, so widgets are usable for post-processing with
no platform at all.

## 9. Custom renderers per data type

Allow protocols (or users) to register a `(DataType) -> DataFrame` or
`(Completed) -> displayable` override, for data layouts the generic tabulation
does not handle well (2-D sweeps, randomized benchmarking sequences).
Registration through a simple dictionary in the core, keyed by class.
