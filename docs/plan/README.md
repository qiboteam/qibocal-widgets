# Plans

Design notes for `qibocal-widgets` and the roadmap of possible extensions.
Nothing in this folder beyond [architecture.md](architecture.md) is
implemented: the other documents are proposals, roughly ordered by how close
they are to the current scope.

| Document | Content | Status |
| --- | --- | --- |
| [architecture.md](architecture.md) | How the current minimal product works, and the alternatives considered | implemented |
| [display-features.md](display-features.md) | Richer rendering of executions: results, parameters, history, comparisons | proposal |
| [interactive-execution.md](interactive-execution.md) | Parameter forms, live acquisition, cell-level control of phases | proposal |
| [remote-executor.md](remote-executor.md) | Running protocols on the lab machine from a notebook elsewhere ([#1](https://github.com/qiboteam/qibocal-widgets/issues/1)) | implemented, follow-ups listed |
| [slurm-monitor.md](slurm-monitor.md) | Widgets to submit, follow, and collect Qibocal jobs on a SLURM queue | proposal |
| [packaging-and-ci.md](packaging-and-ci.md) | Release strategy, documentation site, test coverage on real protocols | proposal |

## Scope of the minimal viable product

Reproduce the features of the `show_data()` and `show_reports()` helpers of
[qibolab-simulator](https://github.com/qiboteam/qibolab-simulator/blob/main/notebooks/helpers/__init__.py)
without explicit invocation, for both Marimo and Jupyter, sharing as much code
as possible. See [architecture.md](architecture.md) for the outcome.
