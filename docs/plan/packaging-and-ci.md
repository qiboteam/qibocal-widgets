# Packaging, CI, documentation

Status: mostly implemented; publishing waits for Qibocal, and two repository
settings need an administrator. The repository has a `uv` package, tests,
documentation, and workflows reusing `qiboteam/workflows@uv`.

## Done

- **Documentation**: a Sphinx site in `docs/source/` with the Qibo `furo`
  theme, built by `poe docs` and published by `docs.yml` through the reusable
  `latest-stable.yml` workflow (`latest` from `main`, `stable` from tags), live
  at <https://qibo.science/qibocal-widgets/latest/>.
- **Executable documentation**:
  - `poe examples` (part of `poe docs`) executes both example notebooks, which
    tour all the user-facing features on the simulated `qutrits` platform of
    qibolab-simulator (copied in `examples/platforms`, simulator installed by
    the `examples` group, included in `docs`), and exports them with their
    outputs (`marimo export html`, `jupyter nbconvert --execute`, with the
    widget state embedded); the *Examples* page links them. On GitHub's runners the whole documentation
    build, examples included, takes under a minute, and the pages are live.
  - The platform state guide contains doctests on the mock platform, run by
    `poe test-docs`, enabled in the test workflow on Linux.
- **Wheels**: built on every push by `wheels.yml` (publishing disabled, see
  below), including the explorer's browser assets.
- **Real protocols in tests**: Qibocal's `mock` platform is vendored under
  `tests/platforms`; remote, session, and platform state tests run the
  built-in `ramsey_signal` on it.
- **Worker coverage**: the remote worker runs inline in subprocesses, where
  coverage cannot attribute it to its file; its actions are also tested
  in-process (`tests/test_worker.py`), raising its measured coverage from 47%
  to 86%.
- **Windows** is in the test matrix. The tests relying on the POSIX fake
  cluster tools (`sh` scripts and symbolic links on `PATH`) are skipped there;
  everything else, including the notes lock, runs. The first Windows run found
  one non-portable test (a path compared as a string), since fixed; macOS
  passed on all Python versions.
- **Release hygiene**: `CHANGELOG.md`, in the Keep a Changelog format, with
  the unreleased changes.
- **pre-commit.ci settings** (`ci:` in `.pre-commit-config.yaml`): autofix,
  monthly hook updates.

## Pending actions (repository administrators)

- **Codecov token**: the reusable test action fails on Linux when the
  coverage upload fails, and a manually dispatched run showed that no token is
  available: the repository has no `CODECOV_TOKEN` secret, none is inherited
  from the organization (*token length: 0*), and Codecov rejects tokenless
  uploads (*Token required - not valid tokenless upload*). All the tests and
  doctests pass in that run; only the upload fails. Add the secret, then
  restore the `push`, `merge_group`, and `pull_request` triggers of
  `tests.yml`, commented out until then.
- **pre-commit.ci**: enable the app on the repository, as for the other Qibo
  projects; the configuration is ready.

## Remaining

### Dependency on unreleased Qibocal

`pyproject.toml` declares `qibocal>=0.2.7` and pins the `protodev` branch
through `[tool.uv.sources]`, deliberately kept until Qibocal releases the
executor interface. A wheel installed from PyPI would resolve to the released
Qibocal, which lacks it.

- Keep `publish: false` in `wheels.yml` until then.
- Then bump the lower bound to that release, drop the source pin, and enable
  publishing on GitHub releases (`publish` condition and `PYPI_TOKEN` secret
  as in Qibocal).
- Meanwhile, consumers install from git.

### Release process

When publishing becomes possible: bump the static version in `pyproject.toml`,
move the *Unreleased* changelog entries under the new version, tag, and
publish a GitHub release (which triggers the wheel upload and the `stable`
documentation).

## Known issues

- **qibolab signal handlers**: creating a qibolab platform replaces the
  process-wide `SIGINT` and `SIGTERM` handlers (to disconnect instruments when a
  job is cancelled). Marimo relies on those signals to shut its runtime down,
  so `marimo export html` hangs on notebooks creating a platform. The example
  notebooks restore the handlers right after creating each platform, as
  qibolab-simulator's notebook does. The same replacement interferes with
  interrupting cells in live notebooks: worth raising upstream, in qibolab.
- **Kernel messaging in sandboxed environments**: executing the Jupyter
  example occasionally stalls for minutes in some sandboxed environments (the
  kernel idle, its messages delayed over local TCP; IPC transport is
  consistently slower). It never happened on GitHub's runners. `nbconvert`
  runs with a per-cell timeout, so that a stall fails the build instead of
  hanging it.
