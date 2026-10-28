"""A cell submitting again while displayed: run by test_marimo_reactive."""

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
    tick, set_tick = mo.state(0)
    return executor, set_tick, tick


@app.cell
def _(executor, tick):
    tick()
    pending = executor.submit(fake(npoints=3), reuse=True)
    pending
    return (pending,)


@app.cell
def _(set_tick):
    set_tick(1)  # the submitting cell runs again
    return


@app.cell
def _(pending, tick):
    assert pending is not None  # after the submitting cell
    if tick() == 1:
        time.sleep(4)  # keep the kernel alive while the execution completes
    return


if __name__ == "__main__":
    app.run()
