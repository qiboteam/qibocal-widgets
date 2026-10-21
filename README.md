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

`qibocal-widgets` provides a drop-in executor, composed of three roles:
**frontends** displaying every output, a **runner** deciding where the steps
run, and **middleware** wrapping every step. With a frontend, outputs render
themselves:

```python
from qibocal import protocols

from qibocal_widgets import Executor
from qibocal_widgets.marimo import Marimo  # or: qibocal_widgets.jupyter.Jupyter

executor = Executor.create(
    platform=platform, path="var/report", update=False, frontends=[Marimo()]
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
`reports`, `targets`, ...) plus the views registered by frontends. The Marimo and
Jupyter frontends can be registered together. Explicit helpers remain available
when finer control is needed:

```python
from qibocal_widgets.marimo import show_data, show_reports

show_data(completed)
show_reports(completed)
```

Executions produced by a plain `qibocal.Executor` (or loaded from disk) can be
made displayable with `wrap(completed)`, or simply by passing them through any
phase of an executor with the frontend.

The `Remote` runner (`qibocal_widgets.remote`) dispatches the acquisition to
the machine with the instruments, through SLURM and SSH, while fit and report
run locally; named connections are shared with qibocal-report, and the queue
can be followed from the notebook (`executor.runner.monitor()`):

```python
executor = Executor(None, targets=[0, 1], runner=Remote("lab"), frontends=[Marimo()])
```

Every execution is recorded in the executor's session folder, appended for as
long as the instance lives, in the layout of Qibocal's outputs: start a new
folder with `executor.new_session()`, or continue an existing one with
`Executor.attach(path)`. In notebook sessions with a reports folder
(`QIBOCAL_REPORTS_DIR`, set by qibocal-report), the folder defaults to a fresh
subfolder of it, so calibrations show up in its report dashboard;
`reports_dir()` returns the folder.

The calibration state of the platform can be explored and updated by path,
with the same paths as qibolab's `Platform.update` and the qibocal-report
dashboard, from code or with an interactive explorer (Jupyter and Marimo):

```python
state = executor.platform_state
state["parameters.configs.0/drive.frequency"]
state.update({"calibration.single_qubits.0.qubit.frequency_01": 4.1e9})
state.explore(editable=True)
```

Middleware work like in web servers: each one wraps the executor steps
(`acquire`, `fit`, `report`, `update`, and the context lifecycle), and may
post-process every output. See the documentation to write your own frontends,
runners, and middleware.

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

The public interface is made of four modules, which only re-export objects
implemented in the private `qibocal_widgets._core` subpackage:

- `qibocal_widgets`: `Executor`, the base classes of its roles (`Frontend`,
  `Runner` and its default `Local`, `Middleware`), `Completed`, and the
  frontend-agnostic building blocks (`data_frames`, `reports`, `Report`, ...).
- `qibocal_widgets.marimo`: the `Marimo` frontend, `show_data`, `show_reports`,
  `wrap`.
- `qibocal_widgets.jupyter`: the `Jupyter` frontend (rendering with
  `ipywidgets`), `show_data`, `show_reports`, `wrap`.
- `qibocal_widgets.remote`: the `Remote` runner, and connections management.
- `qibocal_widgets.explorer`: the platform state explorer widget.
- `qibocal_widgets.monitor`: the SLURM queue monitor widget.

Inside `_core`: `data` and `reports` (extraction, no frontend import),
`layout` (shared display policy), `completed`, `frontend`, `runner`,
`middleware` and `executor` (the executor and its roles), `marimo` and
`jupyter` (rendering), `remote` (connections, job encoding, transport, and the
self-contained remote worker), `session`, `notes`, and `platforms` (session
folders), `state` and `explorer` (platform states by path, and their widget,
whose browser side is a plain ES module next to it).

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
