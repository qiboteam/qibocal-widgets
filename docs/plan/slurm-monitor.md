# SLURM queue monitor

Status: mostly superseded; one proposal remains. The original idea was a set
of widgets to submit, follow, and collect Qibocal jobs on a SLURM queue from
the notebook. Most of it is now covered by other pieces.

## Superseded

- **Submission and collection of jobs**: the `Remote` runner dispatches each
  step needing the instruments as a blocking `srun` job, optionally through
  SSH, and records its outputs in the executor's session folder (see
  [remote-executor.md](remote-executor.md)). No batch scripts, sidecar files,
  or output conventions are needed.
- **The open questions** of the original proposal are settled there: jobs are
  described in JSON and NPZ (no pickle, no runcards), and SSH goes through
  plain `ssh` with the user's configuration.
- **Platform status widget**: the platform state explorer (#3), with
  comparison against the start of the session.
- **Calibration dashboard**: the report server of qibocal-report serves the
  session folders, and shows the executions and their history.
- **A queue backend in this package**: qibocal-report already reads the queue
  (`squeue`, `sinfo`, over SSH: `qibocal notebook queue`) and shows it in its
  launcher. A second implementation here would duplicate it.

## Remaining

### Queue view in the notebook

A compact, refreshable view of the user's jobs, for the connection of a
`Remote` runner (`executor.runner.queue()`), useful while acquisitions wait in
the queue. It should reuse qibocal-report's queue query (same command, same
parsed fields), possibly moved to a package shared by both, rather than
reimplement it. It becomes more relevant together with asynchronous remote
jobs (follow-up of [remote-executor.md](remote-executor.md)), where pending
executions could link to their job.

## Dropped

- **Instrument health panel** (TWPA pump, temperatures): lab-specific, and
  better served by the labs' own monitoring than by calibration notebooks.
