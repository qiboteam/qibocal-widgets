# SLURM queue monitor

Status: proposal. Labs often run Qibocal on a cluster node attached to the
instruments, through a SLURM queue, while the notebook runs elsewhere. A set
of widgets for submitting, following, and collecting those jobs would close
the loop without leaving the notebook.

## Scope

1. **Queue view**: the user's jobs (`squeue --me`) with state, partition,
   node, elapsed time, auto-refreshing.
2. **Job details**: `scontrol show job`, the tail of stdout/stderr, and for
   Qibocal jobs the output folder with the executions dumped so far.
3. **Submission**: turn a `BoundProtocol` (or a runcard) plus platform and
   targets into a batch script, submit it, and track it.
4. **Collection**: once a job finishes, load its output folder as a history
   (see [display-features.md](display-features.md)) and display executions
   with the same widgets used for local runs.

## Design

### Backend (`qibocal_widgets.slurm`, frontend-agnostic)

- Thin wrappers over the SLURM CLI (`squeue`, `sacct`, `sbatch`, `scancel`,
  `scontrol`) parsing their `--json` or `--parsable2` output into dataclasses.
  No dependency on `pyslurm` (binary, version-bound).
- Remote execution through an optional `ssh` transport (subprocess over
  `ssh host`), since the notebook may not run on a login node. Keep the
  transport pluggable: local, ssh, or a user-provided callable.
- A `Job` dataclass with `id`, `name`, `state`, `elapsed`, `node`,
  `output_path`, and `refresh()`.
- Polling helper with a configurable interval; no daemon threads in the core.

### Frontends

- Marimo: `mo.ui.refresh` drives re-execution of the cell holding the table
  (`mo.ui.table` with row selection); selecting a row shows details in a
  dependent cell. Submission via a form (see
  [interactive-execution.md](interactive-execution.md)).
- Jupyter: `ipywidgets` `Select`/`HTML` updated by an `asyncio` task on the
  kernel's event loop (not a thread), with start/stop buttons.

### Qibocal job convention

To recognise Qibocal jobs and locate their outputs, the submitter writes a
small sidecar file (`<output>/job.json`) with the SLURM job id, platform,
protocol, and targets, and names the job `qibocal:<protocol>`. The queue view
reads sidecars from a configurable root to join queue entries with outputs.

## Open questions

- Authentication for the ssh transport in a notebook context (agent
  forwarding vs. explicit keys).
- Whether the submitted work is a bound protocol pickled to disk, a generated
  Python script, or a Qibocal runcard executed by the `qq` command. The
  runcard route is the most robust across Qibocal versions.
- How much of this belongs in Qibocal itself (a `qibocal.slurm` module) versus
  this package: the backend is frontend-free and could live upstream.

## Other monitoring widgets in the same spirit

- **Platform status**: connected instruments, LO frequencies, qubit
  parameters (`platform.parameters`) as a table, with a diff view against the
  last dumped platform.
- **Calibration dashboard**: a grid of qubits coloured by freshness of the last
  successful calibration of each protocol, from the history of an output
  folder.
- **Instrument health**: TWPA pump status, temperature logs when the lab
  exposes them, as a periodically refreshed panel.
