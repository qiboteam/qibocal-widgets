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

Long acquisitions give no feedback. In increasing order of intrusiveness:

- elapsed and estimated time, from the parameters (`nshots`, sweep sizes): a
  middleware around `acquire`, feasible now;
- a progress callback in Qibocal's executor (upstream), consumed by the same
  middleware;
- partial data for protocols acquiring in batches.

### 5. Background execution

Notebook kernels block during acquisition. A middleware can run the step in a
thread (`mo.Thread` in Marimo) and return a *pending* execution, displayed as
such by the frontends and replaced by the result. Remote runners can do the
same with asynchronous jobs instead of a blocking `srun` (see
[remote-executor.md](remote-executor.md)). Both need the same pending
execution type, and the session to record the execution when it completes.
