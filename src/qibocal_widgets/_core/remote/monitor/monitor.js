// SLURM queue monitor: renders the answer computed in Python, and asks for
// refreshes, on request or periodically. Plain ES module for anywidget.

function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(name, value);
  }
  for (const child of children) {
    if (child !== null && child !== undefined) {
      node.append(typeof child === "string" ? document.createTextNode(child) : child);
    }
  }
  return node;
}

const INTERVALS = [
  [0, "manual"],
  [10, "10 s"],
  [30, "30 s"],
  [60, "1 min"],
  [300, "5 min"],
];

function render({ model, el }) {
  const root = element("div", { class: "qw-monitor" });
  el.append(root);
  const refresh = () => model.send({ kind: "refresh" });

  const title = element("span", { class: "qw-title" });
  const fetched = element("span", { class: "qw-fetched" });
  const button = element("button", { class: "qw-button", title: "Ask the queue now", onclick: refresh }, "⟳");
  const every = element("select", {
    class: "qw-select",
    title: "Automatic refresh",
    onchange: () => {
      model.set("interval", Number(every.value));
      model.save_changes();
    },
  });
  for (const [seconds, label] of INTERVALS) every.append(element("option", { value: seconds }, label));
  const mine = element("input", {
    type: "checkbox",
    onchange: () => {
      model.set("mine", mine.checked);
      model.save_changes();
    },
  });
  const header = element(
    "div",
    { class: "qw-header" },
    title,
    fetched,
    element("span", { class: "qw-spacer" }),
    element("label", { class: "qw-option" }, mine, " mine only"),
    every,
    button,
  );
  const summary = element("div", { class: "qw-summary" });
  const table = element("table", { class: "qw-table" });
  const error = element("div", { class: "qw-error" });
  root.append(header, summary, error, table);

  let timer = null;
  function schedule() {
    if (timer) clearInterval(timer);
    timer = null;
    const seconds = model.get("interval");
    if (seconds > 0) timer = setInterval(refresh, seconds * 1000);
  }

  function chip(label, count, kind) {
    return element("span", { class: `qw-chip qw-${kind}` }, `${label} ${count}`);
  }

  function draw() {
    const partition = model.get("partition");
    const user = model.get("user");
    title.textContent = `queue${partition ? " · " + partition : ""}${user ? " · as " + user : ""}`;
    fetched.textContent = model.get("fetched_at") ? `asked at ${model.get("fetched_at")}` : "";
    every.value = String(model.get("interval"));
    mine.checked = model.get("mine");

    const stats = model.get("summary") || {};
    summary.replaceChildren();
    for (const [state, count] of Object.entries(stats.jobs || {})) {
      summary.append(chip(state.toLowerCase(), count, state.toLowerCase()));
    }
    for (const [state, count] of Object.entries(stats.nodes || {})) {
      summary.append(chip(`nodes ${state.toLowerCase()}`, count, "nodes"));
    }
    if (stats.available === false) summary.append(chip("partition", "down", "down"));

    error.textContent = model.get("error");
    error.style.display = model.get("error") ? "" : "none";

    const jobs = model.get("jobs");
    const head = element(
      "tr",
      {},
      ...["job", "name", "user", "state", "time", "nodes / reason"].map((label) => element("th", {}, label)),
    );
    const rows = jobs.map((job) => {
      const name = element("td", { class: "qw-mono" }, job.name);
      if (job.ours) name.append(element("span", { class: "qw-tag", title: "Submitted by the remote runner" }, "runner"));
      const time = job.time_limit ? `${job.time} / ${job.time_limit}` : job.time;
      const where = job.reason ? `(${job.reason})` : job.nodes;
      return element(
        "tr",
        { class: [job.mine ? "qw-mine" : "", job.ours ? "qw-ours" : ""].join(" ").trim() },
        element("td", { class: "qw-mono" }, job.id),
        name,
        element("td", { class: job.mine ? "qw-strong" : "" }, job.user),
        element("td", { class: `qw-state qw-${(job.state.split(" ")[0] || "").toLowerCase()}` }, job.state),
        element("td", { class: "qw-mono" }, time),
        element("td", { class: "qw-mono" }, where),
      );
    });
    const total = model.get("total");
    const empty =
      jobs.length === 0
        ? element("tr", {}, element("td", { class: "qw-empty", colspan: 6 }, total ? "no jobs of yours" : "no jobs"))
        : null;
    table.replaceChildren(head, ...rows, ...(empty ? [empty] : []));
  }

  for (const name of ["jobs", "summary", "fetched_at", "error", "partition", "user", "mine", "total"]) {
    model.on(`change:${name}`, draw);
  }
  model.on("change:interval", () => {
    draw();
    schedule();
  });
  draw();
  schedule();
  return () => timer && clearInterval(timer);
}

export default { render };
