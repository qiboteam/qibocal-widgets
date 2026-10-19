# Interactive execution

Status: proposal. Goes beyond displaying outputs: drive the executor from
widgets.

## 1. Parameter forms from `Parameters` dataclasses

Qibocal protocols declare their acquisition parameters as dataclasses with
type hints and defaults. A form can be derived automatically:

- Core: introspect the `parameters_type` of a `Protocol` (fields, types,
  defaults, docstrings when available) into a neutral schema.
- Marimo: `mo.ui.dictionary` / `mo.ui.form` built from the schema; the cell
  returns a `BoundProtocol` when submitted.
- Jupyter: `ipywidgets.interactive_output` or a `VBox` of inputs with a "Bind"
  button.

Ranges (`start/end/step` triplets, `("linspace", a, b, n)` tuples) deserve a
dedicated input with a live preview of the number of points.

## 2. Target selection

A multi-select of qubits or pairs populated from the platform (`platform.qubits`,
`platform.pairs`), optionally filtered to the targets supported by the chosen
protocol (`two_qubit_gates`).

## 3. Phase control

A small toolbar on a displayed execution: "Fit", "Report", "Update" buttons
calling the executor's phases on the displayed object and re-rendering. This
is natural in Jupyter (buttons mutate an `Output`); in Marimo it maps to
`mo.ui.run_button` cells.

## 4. Live acquisition progress

Long acquisitions give no feedback today. Options, in increasing order of
intrusiveness:

- time elapsed / estimated, from `Parameters.nshots` and sweep sizes;
- a progress callback hook in Qibocal's executor (upstream change), consumed by
  a progress bar widget;
- partial data streaming for protocols acquiring in batches (as wideband
  spectroscopy does), re-rendering the data tab while running.

The first is implementable now; the others need coordination with Qibocal.

## 5. Running in a background thread

Notebook kernels block during acquisition. For Jupyter, run the executor call
in a thread and update an `Output` widget from the main loop; Marimo has
`mo.Thread` and a documented pattern for the same. The widget executor can
offer `executor.submit(bound, ...)` returning a future whose display shows
status, then the result.

## 6. Notes and annotations

Qibocal `protodev` attaches `notes` to executions and outputs. A text area on
the displayed execution to add a note, written through `Completed.notes` and
`dump_notes()`, keeps the lab logbook next to the data.
