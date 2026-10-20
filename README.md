# qibocal-widgets

Notebook integration for the [Qibocal](https://github.com/qiboteam/qibocal)
executor, for both [Marimo](https://marimo.io) and
[Jupyter](https://jupyter.org).

Documentation: <https://qibo.science/qibocal-widgets/latest/>

> **Status**: early development. The package targets the executor interface
> developed on the `protodev` branch of Qibocal, which is not yet released.

## What it does

Qibocal's `Executor` returns a `Completed` object from every phase
(`acquire`, `fit`, `report`, `update`, or the full `executor(bound)` call).
Displaying its content in a notebook used to require wrapping it manually in
dedicated helper functions.

`qibocal-widgets` provides a drop-in executor, extended through plugins. With
a frontend plugin, its outputs render themselves:

```python
from qibocal import protocols

from qibocal_widgets import Executor
from qibocal_widgets.marimo import Marimo  # or: qibocal_widgets.jupyter.Jupyter

executor = Executor.create(
    platform=platform, path="var/report", update=False, plugins=[Marimo()]
)
bound = protocols.ramsey(delay=(10, 1000, 100))

with executor:
    acquired = executor.acquire(bound, targets=[0, 1])
acquired  # the cell output is an accordion with the raw data tables

fitted = executor.fit(acquired)
reported = executor.report(fitted)
reported  # two tabs: raw data and per-target reports (plots + fit table)
```

Every phase returns a `qibocal_widgets.Completed`: a subclass of Qibocal's
`Completed` carrying exactly the same attributes (`data`, `results`,
`reports`, `targets`, ...) plus the views registered by plugins. The Marimo and
Jupyter plugins can be registered together. Explicit helpers remain available
when finer control is needed:

```python
from qibocal_widgets.marimo import show_data, show_reports

show_data(completed)
show_reports(completed)
```

Executions produced by a plain `qibocal.Executor` (or loaded from disk) can be
made displayable with `wrap(completed)`, or simply by passing them through any
phase of an executor with the plugin.

Plugins work like web-server middleware: each one wraps the executor steps
(`acquire`, `fit`, `report`, `update`, and the context lifecycle), and may
post-process every output. See the documentation to write your own.

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

The public interface is made of three modules, which only re-export objects
implemented in the private `qibocal_widgets._core` subpackage:

- `qibocal_widgets`: `Executor`, `Plugin`, `Completed`, and the
  frontend-agnostic building blocks (`data_frames`, `reports`, `Report`, ...).
- `qibocal_widgets.marimo`: the `Marimo` plugin, `show_data`, `show_reports`,
  `wrap`.
- `qibocal_widgets.jupyter`: the `Jupyter` plugin (rendering with
  `ipywidgets`), `show_data`, `show_reports`, `wrap`.

Inside `_core`: `data` and `reports` (extraction, no frontend import),
`layout` (shared display policy), `plugin` and `executor` (the plugin
machinery), `marimo` and `jupyter` (rendering).

Other folders:

- `examples/`: a Marimo and a Jupyter notebook.
- `docs/source/`: Sphinx documentation, published at
  <https://qibo.science/qibocal-widgets/latest/>.
- `docs/plan/`: design notes and the roadmap of possible extensions.

## Development

```sh
uv sync --all-extras --group tests --group analysis --group docs
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run --with poethepoet poe docs  # HTML in docs/build/html
```

Continuous integration reuses the
[qiboteam/workflows](https://github.com/qiboteam/workflows) reusable
workflows, like Qibocal itself.
