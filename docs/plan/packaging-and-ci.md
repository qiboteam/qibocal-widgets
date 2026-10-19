# Packaging, CI, documentation

Status: proposal. The repository already has a `uv` package, tests, and
workflows reusing `qiboteam/workflows@uv`. This note lists what remains.

## Dependency on unreleased Qibocal

`pyproject.toml` declares `qibocal>=0.2.7` and pins the `protodev` branch
through `[tool.uv.sources]`. This keeps the wheel metadata valid, but a wheel
installed from PyPI would resolve to the released Qibocal, which lacks the
`Executor`/`Completed` interface.

- Keep `publish: false` in `wheels.yml` until Qibocal ships the interface.
- When it does, bump the lower bound to that release and enable publishing on
  GitHub releases (`publish` condition copied from Qibocal's own workflow,
  with the `PYPI_TOKEN` secret).
- Meanwhile, consumers install from git (`uv add git+https://github.com/
  qiboteam/qibocal-widgets`).

## Test matrix

- Windows is excluded for now (Qibocal's own tests run there; nothing in this
  package is platform specific, so it can be added once the Qibocal git
  dependency proves to install reliably on Windows runners).
- Tests use a fake protocol and a platform-less executor, so they run without
  Qibolab platforms. Add a second layer running one real protocol
  (`ramsey_signal`) on Qibocal's `mock` platform: this requires either
  vendoring the mock platform folder under `tests/platforms` or Qibocal
  shipping it in the package. The smoke test performed during development
  used the former.
- Coverage upload relies on Codecov through the reusable workflow; configure
  the `CODECOV_TOKEN` secret in the repository (tokenless upload works for
  public pull requests only).

## Documentation

Implemented: a Sphinx site in `docs/source/` with the Qibo `furo` theme,
built by `poe docs` and published by `docs.yml` through the reusable
`latest-stable.yml` workflow (`latest` from `main`, `stable` from tags) at
<https://qibo.science/qibocal-widgets/>. Remaining:

- Embed the Marimo example as a rendered page (`marimo export html`, or the
  `marimo` Sphinx integration); it needs a platform, so it depends on the mock
  platform being available, see above.
- Same for the Jupyter example (`nbsphinx` or `myst-nb` with execution).
- Enable `test-docs` (doctests) in the test workflow once the docs contain
  runnable examples.

## Pre-commit / prek

`.pre-commit-config.yaml` mirrors Qibocal's. Qibolab-simulator uses `prek`
with a `prek.toml`; either tool works with the same hooks. Enable
`pre-commit.ci` on the repository as the other Qibo projects do.

## Release hygiene

- Version is static in `pyproject.toml`; adopt the same bump process as
  Qibocal (manual bump + GitHub release).
- Add a `CHANGELOG.md` once the first release is cut.
