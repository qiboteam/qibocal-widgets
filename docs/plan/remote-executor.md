# Remote executor

Status: proposal, open questions below. Tracks
[#1](https://github.com/qiboteam/qibocal-widgets/issues/1), following
[qiboteam/qibocal#1210](https://github.com/qiboteam/qibocal/issues/1210).

Goal: run protocols on a machine with access to the instruments, while the
notebook runs elsewhere, and freely combine this with the notebook executors.

## Settled: cut at the `Executor` level

As argued in #1, dispatching at the `Executor` level (rather than
`platform.execute()`) reuses the most tested path of Qibocal: on the remote
side, a plain `qibocal.Executor` runs individual protocols, as it always has.

### Only `acquire` and `update` need the instruments

Checked on `protodev`: none of the 73 `fit` and 67 `report` callbacks of the
built-in protocols takes the platform. So the split is:

| Phase | Runs | Why |
| --- | --- | --- |
| `acquire` | remote | needs the connected platform |
| `fit` | local | pure function of data; cheap to re-run with other settings |
| `report` | local | pure function of data and results; figures never travel |
| `update` | remote | mutates the platform that lives remotely |

This departs slightly from #1 (which lists reports among the serialized
objects): reports need not travel at all, and neither do Plotly versions need
to match. Data has to travel anyway, to be displayed.

### Data and results travel with Qibocal's own format

`Data.save`/`load` and `Results.save`/`load` (JSON + NPZ) already round-trip
every protocol output, and are what Qibocal writes to disk. Checked on
`ramsey_signal`: `data.json` + `data.npz`, loaded back into the protocol's
`data_type`. No new serialization format is needed for outputs.

### Composition with the notebook executors: cooperative mixins

`RemoteExecutor(qibocal.Executor)` overrides only `acquire`, `update`, and the
context manager (`__enter__`/`__exit__` open and close a remote session
instead of connecting a local platform). The widget executors already override
every phase as `self._wrap(super().<phase>(...))`, so stacking them works
through the MRO:

```python
class MarimoRemoteExecutor(MarimoExecutor, RemoteExecutor):
    pass
```

Checked with a stub remote: `MarimoRemoteExecutor(...)(bound)` acquires
through the remote stub, fits and reports locally, and returns a
`MarimoCompleted`. Each piece also works alone (`RemoteExecutor` returns plain
`Completed`; `MarimoExecutor` stays local).

The transport is a constructor argument of `RemoteExecutor`, not a class
dimension, so new transports do not multiply classes. Ready-made
combinations (`MarimoRemoteExecutor`, `JupyterRemoteExecutor`) are exported by
the frontend modules.

The local executor has no platform (`platform=None`); parameters of the
remote platform can be queried through the transport for display.

## Open: transport

This is the decision that depends on how labs reach the instruments, and it
also constrains protocol serialization (next section).

### A. Long-running server on the lab machine

A small RPC server wraps one `qibocal.Executor`; the client calls `acquire` /
`update` over HTTP (stdlib or a light dependency), through an SSH tunnel.

- Stateful session: the platform stays connected between calls, and updates
  persist naturally, exactly like a local executor.
- Lowest latency; best fit for interactive notebook use.
- Needs a reachable process, and authentication.
- Conflicts with queue-managed hardware: the server would have to hold the
  queue allocation for its whole lifetime.

### B. Batch jobs through a queue (the #1210 route)

Each remote phase becomes a job folder (serialized inputs + an entry point),
submitted through a user-registered script (`srun -p <partition> ...`); the
client waits for, and loads, the output folder (Qibocal's own dump).

- Fits labs where instruments are only reachable through SLURM partitions.
- Stateless: each job re-creates the platform, so updates must be persisted
  between jobs (shipping the platform with each job, or dumping it back).
- Queue latency per phase; completion detection needed (polling the output
  folder, or `sacct`). Pairs with the [SLURM monitor](slurm-monitor.md).
- No dependency beyond SSH/shared filesystem.

### C. Dask (`distributed`, optionally `dask-jobqueue`)

A dask [actor](https://distributed.dask.org/en/stable/actors.html) holds the
`qibocal.Executor` on a worker; its methods are the RPC API.
`dask-jobqueue` provides workers through SLURM.

- Covers both interactive and queue-based use with one mechanism.
- Serialization (cloudpickle) and futures for free.
- Heavy dependency, environments must match closely on both sides, and actors
  are a less mainstream corner of dask.

**Recommendation**: define a minimal `Transport` interface
(`open`/`close`/`acquire`/`update`), with an in-process transport for tests,
and implement **A first** if labs can run a long-lived process next to the
instruments, otherwise **B first**. C is attractive but heavy; worth
prototyping only if both interactive and queue use are needed soon.

## Open: how protocols travel

The remote side must run the same acquisition (and update) code.

1. **By reference** (plain `pickle`): works for all built-in and importable
   protocols (checked: a bound `ramsey_signal` is 530 bytes). Fails for
   protocols defined in a notebook cell. Requires compatible Qibocal versions.
2. **By value** (`cloudpickle`): also ships notebook-defined protocols.
   Requires the same Python minor version, and means executing arbitrary code
   on the lab machine: acceptable only behind authentication, between trusted
   parties.
3. **By name + parameters** (runcard-like: protocol id, targets, parameters as
   a dictionary, as Qibocal runcards already do): no code shipped, robust
   across versions, safest; only registered protocols.

**Recommendation**: 1 by default, which is the simplest and covers the
built-in protocols. Add 3 if version skew or security becomes a concern, and
2 as an explicit opt-in for custom protocols.

## Questions to settle before implementing

1. How do labs reach the instruments: a host where a long-lived process can
   run (A), only through SLURM jobs (B), or both?
2. Must notebook-defined protocols run remotely, or are importable protocols
   enough for a start?
3. Is the remote side trusted (same team, behind SSH), or should the server
   refuse to execute shipped code?
