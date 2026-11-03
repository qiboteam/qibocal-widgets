// Progress of a pending execution: phase, executions and batches estimated,
// clocks and bars run here, from the event times. Plain ES module.

function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") node.className = value;
    else if (name === "style") node.style.cssText = value;
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

function duration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return `${(seconds * 1e3).toPrecision(3).replace(/\.?0+$/, "")} ms`;
  if (seconds < 60) return `${seconds.toPrecision(3).replace(/\.?0+$/, "")} s`;
  let total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  total -= minutes * 60;
  if (minutes < 60) return `${minutes} min ${total} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
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
  // the kernel's clock, as of the creation of the view
  const offset = Date.now() / 1000 - model.get("clock");
  const now = () => Date.now() / 1000 - offset;
  const root = element("div", { class: "qw-progress" });
  el.append(root);
  const live = []; // updated on every tick: () => void

  function bar(start, estimate, { indeterminate = false } = {}) {
    const fill = element("div", { class: "qw-fill" });
    const track = element("div", { class: "qw-track" }, fill);
    if (indeterminate) {
      track.classList.add("qw-indeterminate");
      return track;
    }
    live.push(() => {
      const elapsed = now() - start;
      const ratio = estimate > 0 ? elapsed / estimate : 1;
      fill.style.width = `${Math.min(1, ratio) * 100}%`;
      track.classList.toggle("qw-over", ratio > 1);
    });
    return track;
  }

  function timing(start, estimate) {
    const text = element("span", { class: "qw-timing" });
    live.push(() => {
      const elapsed = now() - start;
      const over = elapsed - estimate;
      text.textContent =
        over > 0
          ? `${duration(elapsed)} · ${duration(over)} over ≈${duration(estimate)}`
          : `${duration(elapsed)} of ≈${duration(estimate)}`;
    });
    return text;
  }

  function row(label, detail, start, estimate, title) {
    return [
      element("div", { class: "qw-label", title }, label, detail ? element("span", { class: "qw-detail" }, detail) : null),
      bar(start, estimate),
      timing(start, estimate),
    ];
  }

  function estimatesTable(executions) {
    const rows = [];
    executions.forEach((execution, k) => {
      rows.push(
        element(
          "tr",
          {},
          element("td", {}, `execution ${k + 1}`),
          element("td", {}, "qibolab"),
          element("td", {}, duration(execution.estimate)),
          element("td", {}, duration(execution.measured))
        )
      );
      execution.batches.forEach((batch, j) =>
        rows.push(
          element(
            "tr",
            { class: "qw-sub" },
            element("td", {}, `batch ${k + 1}.${j + 1}`),
            element("td", {}, "driver"),
            element("td", {}, duration(batch.estimate)),
            element("td", { title: "until the next event: run, fetch, and preparation of the next" }, duration(batch.measured))
          )
        )
      );
    });
    const details = element(
      "details",
      { class: "qw-estimates", open: model.get("unfolded") },
      element("summary", {}, `Estimates (${rows.length})`),
      element(
        "table",
        {},
        element(
          "thead",
          {},
          element("tr", {}, ...["", "by", "estimated", "measured"].map((h) => element("th", {}, h)))
        ),
        element("tbody", {}, ...rows)
      )
    );
    details.addEventListener("toggle", () => {
      model.set("unfolded", details.open);
      model.save_changes();
    });
    return details;
  }

  function draw() {
    live.length = 0;
    const status = model.get("status");
    const phase = model.get("phase");
    const executions = model.get("executions");
    const started = model.get("started");
    const ended = model.get("ended");
    const processing = status === "processing";
    const label = processing ? phase || "processing" : PHASES[phase] || PHASES[status] || status;

    const since = element("span", { class: "qw-clock", title: "since submitted" });
    const submitted = model.get("submitted");
    live.push(() => (since.textContent = clock(now() - submitted)));
    const header = element(
      "div",
      { class: "qw-header" },
      element("span", { class: `qw-indicator qw-${processing ? "processing" : status}` }),
      element("span", { class: "qw-name" }, model.get("name")),
      element("span", { class: `qw-phase qw-${processing ? "processing" : "acquiring"}` }, label),
      since
    );

    const body = [];
    if (status === "acquiring" && executions.length && ended === null) {
      const grid = element("div", { class: "qw-grid" });
      const k = executions.length;
      const current = executions[k - 1];
      grid.append(
        ...row(`Execution ${k}`, "/ ?", current.started, current.estimate, "platform.execute() calls, estimated by qibolab; their number is not known in advance")
      );
      const batches = current.batches;
      if (batches.length) {
        const batch = batches[batches.length - 1];
        grid.append(
          ...row(`Batch ${batches.length}`, "/ ?", batch.started, batch.estimate, "batches of the execution, estimated by the driver (e.g. Qblox)")
        );
      }
      if (k > 1 && started !== null) {
        // completed executions as refined by their batches, the current one
        // as a whole (more batches to come)
        const estimated = executions.reduce(
          (sum, e) =>
            sum +
            (e.batches.length && e.measured !== null
              ? e.batches.reduce((s, b) => s + b.estimate, 0)
              : e.estimate),
          0
        );
        const total = element("span", { class: "qw-timing" });
        live.push(() => (total.textContent = `${duration(now() - started)} · estimated so far ${duration(estimated)}`));
        grid.append(element("div", { class: "qw-label" }, "Acquisition"), element("div", {}), total);
      }
      body.push(grid);
    } else if (processing || phase === "transferring" || phase === "queued" || phase === "starting" || status === "waiting") {
      body.push(element("div", { class: "qw-grid qw-single" }, bar(0, 0, { indeterminate: true })));
    }
    if (executions.length) body.push(estimatesTable(executions));
    root.replaceChildren(header, ...body);
    tick();
  }

  function tick() {
    for (const update of live) update();
  }

  const timer = setInterval(tick, 250);
  for (const name of ["status", "phase", "executions", "started", "ended"]) {
    model.on(`change:${name}`, draw);
  }
  draw();
  return () => clearInterval(timer);
}

export default { render };
