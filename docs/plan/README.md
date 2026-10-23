# Plans

Design notes for `qibocal-widgets`, and the roadmap of possible extensions.
[architecture.md](architecture.md) describes what is implemented, and why;
the other documents track one area each, splitting their items into **done**,
**remaining**, and **dropped** (with the reason, so that reconsidered ideas
stay traceable).

| Document | Content | Status |
| --- | --- | --- |
| [architecture.md](architecture.md) | Executor roles, display, sessions, platform states, and the alternatives considered | implemented |
| [remote-executor.md](remote-executor.md) | Running protocols on the machine with the instruments, through SLURM and SSH ([#1](https://github.com/qiboteam/qibocal-widgets/issues/1)) | implemented, follow-ups |
| [display-features.md](display-features.md) | Richer rendering of executions and sessions | proposals |
| [interactive-execution.md](interactive-execution.md) | Driving the executor from widgets | proposals |
| [slurm-monitor.md](slurm-monitor.md) | Following the queue from the notebook | implemented, the rest superseded |
| [packaging-and-ci.md](packaging-and-ci.md) | Release, CI, documentation | mostly implemented, administrator actions pending |

## Origin

The first goal was to reproduce the `show_data()` and `show_reports()`
helpers of
[qibolab-simulator](https://github.com/qiboteam/qibolab-simulator/blob/main/notebooks/helpers/__init__.py)
without explicit invocation, for both Marimo and Jupyter, sharing as much code
as possible. The scope then grew to remote execution (#1), the reports folder
of Qibocamp sessions (#2), platform states (#3), and session folders
(#4).
