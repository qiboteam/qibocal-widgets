// Progress of a pending execution: phase, executions and batches estimated.
// Clocks and bars run here, from the event times. The structure is built once
// and updated in place, and numbers have a fixed width, so that nothing moves
// but the values. Plain ES module for anywidget.

function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value === true) node.setAttribute(name, "");
    else if (value !== undefined && value !== null && value !== false) {
      node.setAttribute(name, value);
    }
  }
  for (const child of children) {
    if (child !== null && child !== undefined && child !== false) {
      node.append(typeof child === "string" ? document.createTextNode(child) : child);
    }
  }
  return node;
}

const FIGURE = "\u2007"; // a space as wide as a digit
const WIDTH = 7; // characters of a duration: "999 ms", "59.9 s", "59:59", "9:59:59"

// A duration with a fixed width (with tabular digits): the format depends on
// the magnitude only, which changes rarely.
function duration(seconds) {
  let text;
  if (seconds === null || seconds === undefined) text = "—";
  else if (seconds < 1) text = `${Math.round(seconds * 1e3)} ms`;
  else if (seconds < 60) text = `${(Math.floor(seconds * 10) / 10).toFixed(1)} s`;
  else text = clock(seconds);
  return text.padStart(WIDTH, FIGURE);
}

function clock(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

const PHASES = {
  waiting: "waiting for the instruments",
  queued: "queued",
  starting: "starting",
  running: "running",
  transferring: "receiving the data",
};

function render({ model, el }) {
  // the kernel's clock, at the latest update
  let offset = Date.now() / 1000 - model.get("clock");
  const now = () => Date.now() / 1000 - offset;
  // at least zero: the clocks are only corrected at each update
  const since = (start) => Math.max(0, now() - start);
  let live = []; // updated on every tick, and on every change

  // -- header: built once ------------------------------------------------------
  const indicator = element("span", { class: "qw-indicator" });
  const phase = element("span", { class: "qw-phase" });
  const submitted = element("span", { class: "qw-clock", title: "since started" });
  const cancel = element(
    "button",
    {
      class: "qw-cancel",
      title: "Cancel: queued jobs are stopped; running ones stop before their next execution on the platform",
      onclick: () => {
        cancel.disabled = true;
        cancel.textContent = "cancelling…";
        model.send({ kind: "cancel" });
      },
    },
    "✕ Cancel"
  );
  const header = element(
    "div",
    { class: "qw-header" },
    indicator,
    element("span", { class: "qw-name" }, model.get("name")),
    phase,
    submitted,
    cancel
  );
  const body = element("div", { class: "qw-body" });
  const root = element("div", { class: "qw-progress" }, header, body);
  el.append(root);

  // -- rows ------------------------------------------------------------------
  // a bar with its numbers: elapsed, estimate, and how much over (reserved)
  function row(label, detail, title, get) {
    const fill = element("div", { class: "qw-fill" });
    const track = element("div", { class: "qw-track" }, fill);
    const elapsed = element("span", { class: "qw-number" });
    const estimate = element("span", { class: "qw-number qw-estimate" });
    const over = element("span", { class: "qw-number qw-over-by" });
    const cells = [
      element("div", { class: "qw-label", title }, label, element("span", { class: "qw-detail" }, detail)),
      track,
      elapsed,
      estimate,
      over,
    ];
    const update = () => {
      const { start, seconds } = get();
      const spent = since(start);
      const ratio = seconds > 0 ? spent / seconds : 1;
      fill.style.width = `${Math.min(1, ratio) * 100}%`;
      track.classList.toggle("qw-over", ratio > 1);
      elapsed.textContent = duration(spent);
      estimate.textContent = `≈${duration(seconds)}`;
      over.textContent = spent > seconds ? `+${duration(spent - seconds).trimStart()}`.padStart(WIDTH + 1, FIGURE) : "";
    };
    return { cells, update };
  }

  function current() {
    const executions = model.get("executions");
    return executions[executions.length - 1];
  }

  function estimatedSoFar() {
    // completed executions as refined by their batches, the current one as a
    // whole (more batches to come)
    return model.get("executions").reduce(
      (sum, e) =>
        sum +
        (e.batches.length && e.measured !== null
          ? e.batches.reduce((s, b) => s + b.estimate, 0)
          : e.estimate),
      0
    );
  }

  // the sections of the body, rebuilt only when their rows change
  function layout() {
    const status = model.get("status");
    const executions = model.get("executions");
    const ended = model.get("ended");
    if (status === "acquiring" && executions.length && ended === null) {
      const batches = current().batches.length > 0;
      return `bars:${batches}:${executions.length > 1}`;
    }
    return status === "processing" ? "processing" : "waiting";
  }

  let built = null;
  let rows = [];
  let labels = {};
  let table = null;

  function build(kind) {
    rows = [];
    labels = {};
    const parts = [];
    if (kind.startsWith("bars")) {
      const [, batches, total] = kind.split(":");
      const grid = element("div", { class: "qw-grid" });
      const execution = row("Execution", "", "platform.execute() calls, estimated by qibolab; their number is not known in advance", () => {
        const e = current();
        return { start: e.started, seconds: e.estimate };
      });
      labels.execution = execution.cells[0].firstChild;
      grid.append(...execution.cells);
      rows.push(execution.update);
      if (batches === "true") {
        const batch = row("Batch", "", "batches of the execution, estimated by the driver (e.g. Qblox)", () => {
          const list = current().batches;
          const b = list[list.length - 1];
          return { start: b.started, seconds: b.estimate };
        });
        labels.batch = batch.cells[0].firstChild;
        grid.append(...batch.cells);
        rows.push(batch.update);
      }
      if (total === "true") {
        const elapsed = element("span", { class: "qw-number" });
        const estimate = element("span", { class: "qw-number qw-estimate", title: "the estimates so far" });
        grid.append(
          element("div", { class: "qw-label", title: "elapsed, and the estimates so far" }, "Acquisition"),
          element("div", {}),
          elapsed,
          estimate,
          element("span", { class: "qw-number qw-over-by" })
        );
        rows.push(() => {
          elapsed.textContent = duration(since(model.get("started")));
          estimate.textContent = `≈${duration(estimatedSoFar())}`;
        });
      }
      parts.push(grid);
    } else {
      // an indeterminate bar, the same element across phases
      parts.push(element("div", { class: "qw-track qw-indeterminate" }, element("div", { class: "qw-fill" })));
    }
    table = element("div", { class: "qw-table" });
    parts.push(table);
    body.replaceChildren(...parts);
    built = kind;
  }

  // the list of the estimates, folded; rebuilt when they change
  let listed = null;
  function estimates() {
    const executions = model.get("executions");
    const key = JSON.stringify(executions.map((e) => [e.measured, e.batches.map((b) => b.measured)]));
    if (key === listed) return;
    listed = key;
    if (!executions.length) {
      table.replaceChildren();
      return;
    }
    const lines = [];
    executions.forEach((execution, k) => {
      lines.push(
        element(
          "tr",
          {},
          element("td", {}, `execution ${k + 1}`),
          element("td", {}, "qibolab"),
          element("td", { class: "qw-number" }, duration(execution.estimate)),
          element("td", { class: "qw-number" }, duration(execution.measured))
        )
      );
      execution.batches.forEach((batch, j) =>
        lines.push(
          element(
            "tr",
            { class: "qw-sub" },
            element("td", {}, `batch ${k + 1}.${j + 1}`),
            element("td", {}, "driver"),
            element("td", { class: "qw-number" }, duration(batch.estimate)),
            element(
              "td",
              { class: "qw-number", title: "until the next event: run, fetch, and preparation of the next" },
              duration(batch.measured)
            )
          )
        )
      );
    });
    const details = element(
      "details",
      { class: "qw-estimates", open: model.get("unfolded") },
      element("summary", {}, `Estimates (${lines.length})`),
      element(
        "table",
        {},
        element("thead", {}, element("tr", {}, ...["", "by", "estimated", "measured"].map((h) => element("th", {}, h)))),
        element("tbody", {}, ...lines)
      )
    );
    details.addEventListener("toggle", () => {
      model.set("unfolded", details.open);
      model.save_changes();
    });
    table.replaceChildren(details);
  }

  function update() {
    const status = model.get("status");
    const name = model.get("phase");
    const processing = status === "processing";
    indicator.className = `qw-indicator qw-${processing ? "processing" : status === "waiting" ? "waiting" : "acquiring"}`;
    phase.className = `qw-phase qw-${processing ? "processing" : "acquiring"}`;
    phase.textContent = processing ? name || "processing" : PHASES[name] || name || PHASES[status] || status;
    // the same element, and size, in every state: only its label changes
    const cancelling = model.get("cancelling");
    cancel.disabled = cancelling || !model.get("cancellable");
    cancel.textContent = cancelling ? "cancelling…" : "✕ Cancel";
    cancel.style.visibility = model.get("cancellable") || cancelling ? "visible" : "hidden";
    const kind = layout();
    if (kind !== built) build(kind);
    if (labels.execution) {
      labels.execution.textContent = `Execution ${model.get("executions").length}`;
    }
    if (labels.batch) labels.batch.textContent = `Batch ${current().batches.length}`;
    estimates();
    tick();
  }

  function tick() {
    submitted.textContent = clock(since(model.get("submitted")));
    for (const refresh of rows) refresh();
  }

  model.on("change:clock", () => {
    offset = Date.now() / 1000 - model.get("clock");
  });
  for (const name of ["status", "phase", "executions", "started", "ended", "cancelling", "cancellable"]) {
    model.on(`change:${name}`, update);
  }
  update();
  const timer = setInterval(tick, 100);
  return () => clearInterval(timer);
}

export default { render };
