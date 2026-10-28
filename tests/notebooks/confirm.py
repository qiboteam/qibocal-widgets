"""Executions waiting for confirmation: run by test_marimo_reactive."""

import marimo

app = marimo.App()

with app.setup:
    import sys
    from pathlib import Path

    import marimo as mo

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from fake import fake
    from qibocal import Executor as QibocalExecutor

    from qibocal_widgets import Executor, Runner
    from qibocal_widgets.marimo import Marimo

    class Counting(Runner):
        count = 0

        def acquire(self, executor, bound, **kwargs):
            Counting.count += 1
            return QibocalExecutor.acquire(executor, bound, **kwargs)


@app.cell
def _():
    executor = Executor(
        None,
        targets=[0, 1],
        update=False,
        runner=Counting(),
        frontends=[Marimo()],
        confirm=True,
    )
    return (executor,)


@app.cell
def _(executor):
    pending = executor.submit(fake(npoints=3), nshots=10)
    pending
    return (pending,)


@app.cell
def _(pending):
    result = pending()
    mo.stop(result is None, mo.md(f"DOWNSTREAM-{pending.status.upper()}"))
    return


@app.cell
def _():
    import time

    time.sleep(1)
    mo.md(f"ACQUISITIONS-{Counting.count}")
    return


if __name__ == "__main__":
    app.run()
