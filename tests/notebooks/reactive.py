"""Background executions in a marimo notebook: run by test_marimo_reactive."""

import marimo

app = marimo.App()

with app.setup:
    import sys
    import time
    from pathlib import Path

    import marimo as mo

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from fake import fake
    from qibocal import Executor as QibocalExecutor

    from qibocal_widgets import Executor, Runner
    from qibocal_widgets.marimo import Marimo

    class Slow(Runner):
        concurrent = True

        def acquire(self, executor, bound, **kwargs):
            time.sleep(1)
            return QibocalExecutor.acquire(executor, bound, **kwargs)


@app.cell
def _():
    executor = Executor(
        None, targets=[0, 1], update=False, runner=Slow(), frontends=[Marimo()]
    )
    return (executor,)


@app.cell
def _(executor):
    pending = executor.submit(fake(npoints=3))
    pending
    return (pending,)


@app.cell
def _(pending):
    result = pending()
    mo.stop(result is None, mo.md("DOWNSTREAM-WAITING"))
    mo.md(f"DOWNSTREAM-RESULT-{len(result.data[0])}-POINTS-{type(pending).__name__}")
    return


@app.cell
def _():
    time.sleep(4)  # keep the kernel alive while the execution completes
    return


if __name__ == "__main__":
    app.run()
