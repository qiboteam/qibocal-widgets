# qibocal-widgets

Notebook integration for the [Qibocal](https://github.com/qiboteam/qibocal)
executor, for both [Marimo](https://marimo.io) and
[Jupyter](https://jupyter.org).

> **Status**: early development. The package targets the executor interface
> developed on the `protodev` branch of Qibocal, which is not yet released.

## What it does

Qibocal's `Executor` returns a `Completed` object from every phase
(`acquire`, `fit`, `report`, `update`, or the full `executor(bound)` call).
Displaying its content in a notebook used to require wrapping it manually in
dedicated helper functions.

`qibocal-widgets` provides drop-in executors whose outputs render themselves:

```python
from qibocal import protocols

# or: from qibocal_widgets.jupyter import JupyterExecutor
from qibocal_widgets.marimo import MarimoExecutor

executor = MarimoExecutor.create(platform=platform, path="var/report", update=False)
bound = protocols.ramsey(delay=(10, 1000, 100))

with executor:
    acquired = executor.acquire(bound, targets=[0, 1])
acquired  # the cell output is an accordion with the raw data tables

fitted = executor.fit(acquired)
reported = executor.report(fitted)
reported  # the cell output has two tabs: raw data and per-target reports (plots + fit table)
```

Every phase returns a `MarimoCompleted` (or `JupyterCompleted`): a subclass of
Qibocal's `Completed` carrying exactly the same attributes (`data`, `results`,
`reports`, `targets`, ...) plus the display protocol of the chosen frontend.
Explicit helpers remain available when finer control is needed:

```python
from qibocal_widgets.marimo import show_data, show_reports

show_data(completed.data)
show_reports(completed.reports)
completed.show_data()  # same, as methods
completed.show_reports()
```

Executions produced by a plain `qibocal.Executor` (or loaded from disk) can be
made displayable with `wrap(completed)`, or simply by passing them through any
phase of a widget executor.

## Installation

```sh
uv add "qibocal-widgets[marimo]"   # or [jupyter], or both
```

Until the targeted Qibocal interface is released, pin Qibocal to the `protodev`
branch in your project (as done in this repository's `pyproject.toml`):

```toml
[tool.uv.sources]
qibocal = { git = "https://github.com/qiboteam/qibocal.git", branch = "protodev" }
```

## Layout

- `qibocal_widgets._core`: frontend-agnostic extraction (data tables as
  `pandas.DataFrame`, normalized reports with Plotly figures and HTML tables).
- `qibocal_widgets._executor`: `WidgetExecutor`, the `Executor` subclass
  re-wrapping the output of every phase into a configurable `Completed`
  subclass.
- `qibocal_widgets.marimo`: `MarimoExecutor`, `MarimoCompleted` (implements
  `_display_`), `show_data`, `show_reports`.
- `qibocal_widgets.jupyter`: `JupyterExecutor`, `JupyterCompleted` (implements
  `_ipython_display_`, rendering with `ipywidgets`), `show_data`,
  `show_reports`.
- `examples/`: a Marimo and a Jupyter notebook.
- `docs/plan/`: design notes and the roadmap of possible extensions.

## Development

```sh
uv sync --all-extras --group tests --group analysis
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Continuous integration reuses the
[qiboteam/workflows](https://github.com/qiboteam/workflows) reusable
workflows, like Qibocal itself.
