import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import os
    import shutil
    from pathlib import Path

    import marimo as mo
    from qibocal import protocols

    from qibocal_widgets import Executor
    from qibocal_widgets.marimo import Marimo, show_data, show_reports

    # Point QIBOLAB_PLATFORMS to a folder containing your platform, e.g. the
    # `tests/platforms` folder of the Qibocal repository for the `mock` one.
    PLATFORM = os.environ.get("QIBOCAL_WIDGETS_PLATFORM", "mock")


@app.cell(hide_code=True)
def _():
    mo.md("""
    # Qibocal executions, displayed implicitly

    With the `Marimo` plugin, every phase of the executor returns an
    execution which renders itself when it is the last expression of a cell.
    """)
    return


@app.cell
def _():
    path = Path("var/report")
    if path.exists():
        shutil.rmtree(path)
    executor = Executor.create(
        path=path, platform=PLATFORM, update=False, plugins=[Marimo()]
    )
    return (executor,)


@app.cell
def _():
    bound = protocols.ramsey_signal(
        delay_between_pulses_start=10,
        delay_between_pulses_end=1000,
        delay_between_pulses_step=50,
    )
    return (bound,)


@app.cell
def _(bound, executor):
    with executor:
        acquired = executor.acquire(bound, targets=[0, 1])
    acquired
    return (acquired,)


@app.cell
def _(acquired, executor):
    fitted = executor.fit(acquired)
    fitted.results
    return (fitted,)


@app.cell
def _(executor, fitted):
    reported = executor.report(fitted)
    reported
    return (reported,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## Explicit helpers

    The same content is available through methods and functions, for custom
    layouts.
    """)
    return


@app.cell
def _(reported):
    mo.hstack([show_data(reported), show_reports(reported)])
    return


if __name__ == "__main__":
    app.run()
