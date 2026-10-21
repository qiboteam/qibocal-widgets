# Packaging, CI, documentation

Status: partly implemented; some actions pending. The repository has a `uv`
package, tests, documentation, and workflows reusing `qiboteam/workflows@uv`.

## Done

- **Documentation**: a Sphinx site in `docs/source/` with the Qibo `furo`
  theme, built by `poe docs` and published by `docs.yml` through the reusable
  `latest-stable.yml` workflow (`latest` from `main`, `stable` from tags), live
  at <https://qibo.science/qibocal-widgets/latest/>.
- **Wheels**: built on every push by `wheels.yml` (publishing disabled, see
  below), including the explorer's browser assets.
- **Real protocols in tests**: Qibocal's `mock` platform is vendored under
  `tests/platforms`; remote, session, and platform state tests run the
  built-in `ramsey_signal` on it.

## Pending actions

- **Test workflow triggers**: the automatic triggers of `tests.yml` are
  commented out, since the reusable test action fails when the Codecov upload
  fails. The repository has no `CODECOV_TOKEN` secret: check whether an
  organization-level one is available (as for other Qibo projects), or add
  one, then restore the `push`, `merge_group`, and `pull_request` triggers.
- **Pre-commit**: `.pre-commit-config.yaml` mirrors Qibocal's; enable
  `pre-commit.ci` on the repository as the other Qibo projects do.

## Remaining

### Dependency on unreleased Qibocal

`pyproject.toml` declares `qibocal>=0.2.7` and pins the `protodev` branch
through `[tool.uv.sources]`. A wheel installed from PyPI would resolve to the
released Qibocal, which lacks the executor interface.

- Keep `publish: false` in `wheels.yml` until Qibocal ships the interface.
- Then bump the lower bound to that release, and enable publishing on GitHub
  releases (`publish` condition and `PYPI_TOKEN` secret as in Qibocal).
- Meanwhile, consumers install from git.

### Test matrix

- Windows is excluded. Besides the Qibocal git dependency, the remote tests
  rely on POSIX fake executables (`sh` scripts and symbolic links on `PATH`);
  they would need a Windows variant, or to be skipped there. The notes lock
  already supports Windows.
- The remote worker runs in subprocesses, so its coverage is not measured;
  enable subprocess coverage collection.

### Executable documentation

- Render the examples in the documentation: the Marimo one with `marimo export
  html`, the Jupyter one with `nbsphinx` or `myst-nb`, both on the vendored mock
  platform.
- Enable `test-docs` (doctests) in the test workflow once the documentation
  contains runnable examples.

### Release hygiene

- Version is static in `pyproject.toml`; adopt Qibocal's bump process (manual
  bump and GitHub release).
- Add a `CHANGELOG.md` with the first release.
