import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import json
    import os
    import shutil
    import signal
    import time
    from pathlib import Path

    import marimo as mo
    from qibocal import Executor as QibocalExecutor
    from qibocal import create_calibration_platform, protocols

    from qibocal_widgets import (
        Executor,
        Middleware,
        PlatformState,
        data_frames,
        reports,
        reports_dir,
    )
    from qibocal_widgets.marimo import Marimo, display, show_data, show_reports, wrap
    from qibocal_widgets.remote import Connection, Remote

    HERE = Path(__file__).resolve().parent
    os.environ["QIBOLAB_PLATFORMS"] = str(HERE / "platforms")

    def qutrits():
        """A fresh simulated platform: two coupled qutrits.

        qibolab replaces the termination handlers, which marimo needs to stop
        its kernel: they are restored right after creating the platform.
        """
        handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        platform = create_calibration_platform("qutrits")
        for number, handler in handlers.items():
            signal.signal(number, handler)
        return platform


@app.cell(hide_code=True)
def _():
    mo.md("""
    # qibocal-widgets in Marimo

    A tour of the features of `qibocal-widgets`, on a simulated platform: the
    `qutrits` platform of [qibolab-simulator](https://github.com/qiboteam/qibolab-simulator),
    copied in `platforms/` next to this notebook.

    The executor is a drop-in replacement of Qibocal's, composed of
    **frontends** (displaying every output), a **runner** (where the steps run),
    and **middleware** (wrapping every step).
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 1. The executor and its session

    Create the executor once, at the beginning of the notebook. Every execution
    is recorded in its *session* folder, in Qibocal's output layout. Within a
    session started by the Qibocal application (or `qibocal notebook`), the
    folder defaults to a fresh subfolder of the session's reports folder
    (`QIBOCAMP_REPORTS_DIR`), so that calibrations show up in its dashboard;
    otherwise, it is given explicitly.
    """)
    return


@app.cell
def _():
    if reports_dir() is None:
        path = HERE / "var" / "session"
        if path.exists():
            shutil.rmtree(path)
    else:
        path = None  # a fresh folder under reports_dir()

    executor = Executor.create(
        path=path,
        platform=qutrits(),
        targets=[0, 1],
        update=True,
        frontends=[Marimo()],
    )
    executor.path
    return (executor,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 2. Implicit display, step by step

    Every step returns an execution which displays itself: raw data after the
    acquisition, then reports (selected by default), with the fit table folded
    above the plots.
    """)
    return


@app.cell
def _(executor):
    bound = protocols.ramsey(delay=(10, 1000, 100))
    with executor:
        acquired = executor.acquire(bound, nshots=500)
    acquired
    return (acquired,)


@app.cell
def _(acquired, executor):
    fitted = executor.fit(acquired)
    ramsey = executor.report(fitted)
    ramsey
    return (ramsey,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    The execution is recorded in the session, where notes can be attached to it
    (and to the session itself): they are shown, and can be added, in the
    report dashboard too.
    """)
    return


@app.cell
def _(executor, ramsey):
    executor.note("Two coupled qutrits, simulated")
    executor.note("Fringes as expected", ramsey)
    {
        "task folder": ramsey.path.relative_to(executor.path),
        "notes": [note.content for note in executor.session.notes(ramsey)],
    }
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 3. Updating the platform

    A full execution (`executor(bound)`) acquires, fits, reports, and, with
    the executor's `update=True`, updates the platform. A snapshot of the platform state
    taken before shows what changed.
    """)
    return


@app.cell
def _(executor, ramsey):
    # after the previous section, to keep the session order
    assert ramsey is not None
    start = executor.platform_state.snapshot()
    with executor:
        rabi = executor(
            protocols.rabi_amplitude_signal(
                min_amp=0.0, max_amp=0.6, step_amp=0.03, pulse_length=40
            ),
            nshots=500,
        )
    rabi
    return rabi, start


@app.cell
def _(executor, rabi, start):
    assert rabi is not None
    executor.platform_state.diff(start)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 4. Exploring and editing the platform state

    The explorer shows parameters and calibration by path, highlighting the
    differences with the snapshot. Its navigation bar accepts paths, or pasted
    code; buttons copy paths and values; with `editable=True`, edits go through
    the same API, and show the equivalent code.
    """)
    return


@app.cell
def _(executor, rabi, start):
    assert rabi is not None
    executor.platform_state.explore(
        "native_gates.single_qubit.0", editable=True, compare=start
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    The same paths work from code, in any of the forms the explorer accepts:
    full paths, paths within a document (as copied from the dashboard), or
    pasted code.
    """)
    return


@app.cell
def _(executor, rabi):
    assert rabi is not None
    state = executor.platform_state
    frequency = "parameters.configs.0/drive.frequency"
    before = state[frequency]
    state.update({"configs.0/drive.frequency": before + 1e6})
    {
        "before": before,
        "after": state[frequency],
        "resolved": state.resolve(f'executor.platform_state["{frequency}"]'),
        "qubit frequencies": state.find("frequency_01"),
        "session start": PlatformState.load(executor.path / "platform")[frequency],
    }
    return (state,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 5. Explicit helpers

    For custom layouts, the views are available explicitly, as well as the
    frontend-agnostic content (tables and normalized reports). Executions from a
    plain Qibocal executor are made displayable with `wrap`.
    """)
    return


@app.cell
def _(ramsey):
    mo.ui.tabs(
        {
            "show_data": show_data(ramsey),
            "show_reports": show_reports(ramsey),
            "display": display(ramsey),
        }
    )
    return


@app.cell
def _(ramsey):
    frames = data_frames(ramsey.data)
    normalized = reports(ramsey)
    mo.vstack(
        [
            mo.md(
                f"`data_frames`: {len(frames)} tables, columns {list(frames[0].columns)}"
            ),
            mo.md(
                f"`reports`: {len(normalized[0].figures)} figure(s) per target, "
                f"fit table of {len(normalized[0].table)} characters"
            ),
        ]
    )
    return


@app.cell
def _():
    _platform = qutrits()
    _plain = QibocalExecutor(_platform, targets=[0], update=False)
    _platform.connect()
    _completed = _plain(protocols.ramsey(delay=(10, 1000, 100)), nshots=200)
    _platform.disconnect()
    wrap(_completed)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 6. Middleware

    Middleware wrap every step, like in web servers. A timer, around the
    acquisition, on a second executor appending to the same session folder
    (`Executor.attach`, e.g. after restarting the kernel): it restores the
    latest recorded platform state, so the calibration continues from there.
    """)
    return


@app.cell
def _(executor, state):
    assert state is not None

    class Timer(Middleware):
        def __init__(self):
            self.times = []

        def acquire(self, executor, call_next, *args, **kwargs):
            start = time.perf_counter()
            completed = call_next(*args, **kwargs)
            self.times.append(time.perf_counter() - start)
            return completed

    timer = Timer()
    attached = Executor.attach(
        executor.path,
        platform=qutrits(),
        targets=[0, 1],
        update=False,
        middleware=[timer],
        frontends=[Marimo()],
    )
    with attached:
        attached(protocols.ramsey(delay=(10, 1000, 100)), nshots=500)
    {
        "acquisition time": f"{timer.times[0]:.1f} s",
        "restored frequency": attached.platform_state["configs.0/drive.frequency"],
        "history": json.loads((attached.path / "history.json").read_text()),
    }
    return (attached,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 7. Sessions on disk

    Recorded executions can be loaded back, displayed, and the executor can
    move on to a new session folder, for instance for a new cooldown.
    """)
    return


@app.cell
def _(attached):
    history = json.loads((attached.path / "history.json").read_text())
    loaded = attached.load(attached.path / "data" / history[0])
    loaded
    return (loaded,)


@app.cell
def _(attached, loaded):
    assert loaded is not None
    _first = attached.path
    attached.new_session(_first.parent / "next")
    {"previous session": _first.name, "new session": attached.path.name}
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 8. Remote execution

    The `Remote` runner sends the acquisitions to the machine with the
    instruments, through SLURM and SSH, while fit and report run locally.
    Without options it dispatches nothing, so the same notebook also runs on the
    compute node itself, as here.
    """)
    return


@app.cell
def _():
    _local = Executor(
        qutrits(), targets=[0], update=False, runner=Remote(), frontends=[Marimo()]
    )
    with _local:
        _passthrough = _local(protocols.ramsey(delay=(10, 1000, 100)), nshots=200)
    _passthrough
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    On a laptop, the connection reaches the access node over SSH, and submits
    every acquisition to the queue. Connections can also be stored by name
    (`save_connection`), in the configuration shared with Qibocamp. The
    environment on the remote machine is installed separately
    (`remote.install()`), and the queue can be followed from here.
    """)
    return


@app.cell
def _():
    lab = Remote(
        Connection(
            ssh="-J bastion me@login",
            queue="qpu",
            slurm="--time=10",
            platform="qutrits",
            requirements="qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev",
        )
    )
    _view = (
        Remote(queue=lab.connection.queue).monitor()
        if shutil.which("squeue")
        else mo.md("*No SLURM here: `lab.monitor()` would show the queue of `qpu`.*")
    )
    mo.vstack([mo.md(f"`{lab!r}`"), _view])
    return


if __name__ == "__main__":
    app.run()
