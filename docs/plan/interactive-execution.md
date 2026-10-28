# Interactive execution

Status: proposals. Goes beyond displaying outputs: drive the executor from
widgets. The executor roles give each item a natural home: forms produce
bound protocols outside the executor, toolbars are views of a frontend (which
receives the executor in `Frontend.attach`), progress and background execution
are middleware or runners.

## Done

- **Notes, from code**: `executor.note(text)` and `executor.note(text,
  completed)` write to Qibocal's `notes.json`, shared with the Qibocamp
  dashboard (see [architecture.md](architecture.md)).
- **Platform parameters, interactively**: browsing and editing the platform
  state is the explorer of `executor.platform_state.explore(editable=True)`
  (#3).

## Remaining

### 1. Parameter forms from `Parameters` dataclasses

Qibocal protocols declare their acquisition parameters as dataclasses with
type hints and defaults, from which a form can be derived:

- core: introspect `Protocol.parameters_type` (fields, types, defaults,
  docstrings) into a neutral schema;
- Marimo: `mo.ui.dictionary` / `mo.ui.form` from the schema, the cell returning
  a `BoundProtocol`;
- Jupyter: a `VBox` of inputs with a *Bind* button.

Ranges (`start`/`end`/`step` triplets, `("linspace", a, b, n)` tuples) deserve
a dedicated input with a preview of the number of points.

### 2. Target selection

A multi-select of qubits or pairs, populated from the platform state (the
`single_qubits` and `two_qubits` of the calibration), so that it works with
remote runners too, filtered by the protocol's `two_qubit_gates`.

### 3. Phase control and notes on displayed executions

A small toolbar on a displayed execution: *Fit*, *Report*, *Update* buttons
calling the executor on that execution, and a text field adding a note to it
(`executor.note(text, completed)`). It requires frontends to keep the executor
received in `attach`, and re-render in place: natural in Jupyter (an `Output`
widget), mapped to `mo.ui.run_button` cells in Marimo.

### 4. Acquisition progress

Done, for background executions: the estimates logged by qibolab
(`Platform.execute`) and refined by drivers (Qblox, before each batch) are
captured by a logger filter, in the acquiring thread or in the remote worker
(streamed as `QIBOCAL_WIDGETS_PROGRESS` lines), and displayed as a progress bar
(a CSS animation: no periodic refresh), restarting on each estimate.

Remaining, in increasing order of intrusiveness:

- protocols executing the platform several times log one estimate per
  execution, each restarting the bar: an overall estimate needs the number of
  executions, which only the protocol knows;
- the log messages are scraped, and their loggers named: a structured hook in
  qibolab (e.g. an estimate callback in the execution parameters) would be
  sturdier, and give the total number of batches, now shown as
  `batches done: n/?`
  ([#11](https://github.com/qiboteam/qibocal-widgets/issues/11));
- a progress callback in Qibocal's executor (upstream);
- partial data for protocols acquiring in batches.

### 5. Background execution

Done: `Executor.submit` returns a `Pending` execution (a future, with a
blocking `result()` and `await` support), runs the workflow in a thread, and
processes executions in submission order; runners declare whether their
acquisitions may overlap (`Runner.concurrent`). Frontends render pending
executions (`Frontend.render_pending`): Jupyter replaces the state with the
result when ready, on the kernel's main thread. In Marimo
(`Frontend.background`), executions run in `mo.Thread` and pending executions
are `mo.state` getters (a `State` subclass): cells referencing them run again
on completion, `pending()` peeks without blocking, and a spinner displayed by
the submitting cell is replaced by the result; nothing blocks, so explorers and
monitors stay interactive. `reuse=True` avoids repeated acquisitions through the
session records (a key file per task), instead of caching data with
`mo.cache`. Remaining: detached remote jobs
([#8](https://github.com/qiboteam/qibocal-widgets/issues/8)), cancellation of
pending executions.
