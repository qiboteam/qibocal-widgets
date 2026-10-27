import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup(hide_code=True):
    import json
    import os
    import shutil
    from pathlib import Path

    import marimo as mo
    from qibocal import protocols

    from qibocal_widgets import Executor, Session, reports_dir
    from qibocal_widgets.marimo import Marimo
    from qibocal_widgets.remote import Connection, Remote, config_path, connections

    HERE = Path(__file__).resolve().parent


@app.cell(hide_code=True)
def _():
    mo.md("""
    # Remote execution, in Marimo

    Run this notebook where you work (a laptop, or the access node of a
    cluster): every acquisition is sent to the machine with access to the
    instruments, through SSH and SLURM, while fit and report run here. No
    platform is created locally, and no instrument access is needed.

    The machine running the acquisitions needs Qibocal (installed below) and
    the platform, found in the `platforms_dir` of the connection (or through
    its own `QIBOLAB_PLATFORMS`, if not given).
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 1. The connection

    A connection is given inline, or by name. Named connections are stored in
    `remotes.json`, in the configuration shared with Qibocamp, whose desktop
    application can edit them too; `QIBOCAL_WIDGETS_CONNECTION` selects one
    without changing the notebook.

    **Edit the inline connection** to match your cluster, or set
    `QIBOCAL_WIDGETS_CONNECTION` to the name of a stored one.
    """)
    return


@app.cell
def _():
    name = os.environ.get("QIBOCAL_WIDGETS_CONNECTION")
    if name is not None:
        remote = Remote(name)
    else:
        remote = Remote(
            Connection(
                ssh="me@login.cluster",  # ssh arguments, ending with the destination
                queue="qpu",  # SLURM partition with the instruments
                slurm="--time=10",  # further srun options
                platform="qutrits",  # platform name, on the remote machine
                platforms_dir="~/platforms",  # its folder, on the remote machine
                requirements=(
                    "qibocal @ git+https://github.com/qiboteam/qibocal.git@protodev"
                ),
            )
        )
    mo.vstack(
        [
            mo.md(f"`{remote!r}`"),
            mo.md(f"Stored connections, in `{config_path()}`: {sorted(connections())}"),
        ]
    )
    return (remote,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    To store the inline connection, e.g. as `lab`:
    `save_connection("lab", remote.connection)`; then use `Remote("lab")`.

    ## 2. The remote environment

    Acquisitions run in a Python environment on the remote machine. Installing
    it is a separate step, never performed by the acquisitions: it is skipped
    when the requirements did not change, and runs on the access node, outside
    of the queue.
    """)
    return


@app.cell
def _(remote):
    remote.install()
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 3. The executor, without a local platform

    The executor records every execution in its session folder, here, as
    local executions are. Within a Qibocamp session, the folder defaults to its
    reports folder (`QIBOCAMP_REPORTS_DIR`), so that calibrations show up in
    its dashboard.
    """)
    return


@app.cell
def _(remote):
    if reports_dir() is None:
        path = HERE / "var" / "remote"
        if path.exists():
            shutil.rmtree(path)
    else:
        path = None

    executor = Executor(
        None,
        path=path,
        targets=[0, 1],
        update=True,
        runner=remote,
        frontends=[Marimo()],
    )
    executor.path
    return (executor,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    The platform state is asked to the remote machine, the first time it is
    needed: it can be explored, and edited, as a local one. Edits travel with
    the next acquisitions.
    """)
    return


@app.cell
def _(executor):
    start = executor.platform_state.snapshot()
    executor.platform_state.explore("native_gates.single_qubit.0")
    return (start,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 4. Acquiring in the background

    The acquisition is a job in the queue (named `qibocal-widgets-acquire`).
    `executor.submit` returns at once, so the notebook stays interactive while
    the job waits: the platform explorer and the queue monitor keep working.
    The cell shows a spinner, replaced by the result when it arrives; the data
    are recorded in the session, fitted and reported here.

    With `reuse=True`, running the cell again (e.g. after editing an upstream
    cell) returns the identical execution instead of acquiring again: the one
    still running, or the one recorded in the session.
    """)
    return


@app.cell
def _(executor, start):
    assert start is not None
    pending = executor.submit(
        protocols.ramsey(delay=(10, 1000, 100)), nshots=500, reuse=True
    )
    pending
    return (pending,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    In Marimo, a pending execution is reactive state: the cells referencing it
    run again when it completes. `pending()` is the result, or `None` while
    running: with `mo.stop`, the cell waits without blocking the notebook.
    (`await pending` works too, but holds the notebook until the result.)
    """)
    return


@app.cell
def _(executor, pending):
    ramsey = pending()
    mo.stop(ramsey is None, mo.md("*Waiting for the Ramsey acquisition…*"))
    executor.note("Acquired remotely", ramsey)
    ramsey.results
    return (ramsey,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 5. Several jobs, and remote updates

    Submitted executions are queued together. They are recorded, fitted, and
    update the platform in submission order, whatever the order their jobs
    complete in; each acquisition uses the platform state at the time it
    starts.

    Without a local platform, updates run on the access node, outside of the
    queue; the runner keeps the new state, sends it with the next jobs, and the
    session records it (`new_platform/`).
    """)
    return


@app.cell
def _(executor, ramsey):
    assert ramsey is not None
    rabi = executor.submit(
        protocols.rabi_amplitude_signal(
            min_amp=0.0, max_amp=0.6, step_amp=0.03, pulse_length=40
        ),
        nshots=500,
        reuse=True,
    )
    rabi
    return (rabi,)


@app.cell
def _(executor, ramsey):
    assert ramsey is not None
    check = executor.submit(
        protocols.ramsey(delay=(10, 1000, 200)), nshots=500, reuse=True
    )
    check
    return (check,)


@app.cell
def _(check, executor, rabi, start):
    updated, checked = rabi(), check()
    mo.stop(updated is None or checked is None, mo.md("*Waiting for both jobs…*"))
    executor.platform_state.diff(start)
    return (updated,)


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 6. The queue

    While acquisitions wait in the queue, it can be followed from here: the
    whole partition, with your jobs highlighted and the runner's tagged. The
    monitor refreshes periodically while displayed.
    """)
    return


@app.cell
def _(remote):
    remote.monitor(interval=30)
    return


@app.cell(hide_code=True)
def _():
    mo.md("""
    ## 7. Continuing later

    After restarting the kernel, a new executor attached to the session folder
    continues appending to it; the latest recorded platform state is handed to
    the runner, so that the calibration continues where it was left.
    """)
    return


@app.cell
def _(executor, remote, updated):
    assert updated is not None
    later = Executor(
        None,
        session=Session.attach(executor.path),
        targets=[0, 1],
        update=False,
        runner=Remote(remote.connection),  # a fresh runner, as after a restart
        frontends=[Marimo()],
    )
    {
        "history": json.loads((later.path / "history.json").read_text()),
        "restored": later.platform_state.diff(executor.platform_state) == {},
    }
    return


if __name__ == "__main__":
    app.run()
