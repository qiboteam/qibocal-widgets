// Platform history explorer: entries computed in Python, two of them compared
// (A and B), and restore requests sent back. Plain ES module for anywidget.

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
    if (child !== null && child !== undefined) {
      node.append(typeof child === "string" ? document.createTextNode(child) : child);
    }
  }
  return node;
}

function render({ model, el }) {
  const root = element("div", { class: "qw-history" });
  el.append(root);
  const selected = new Set();
  // radio groups of this explorer only, with others on the same page
  const group = Math.random().toString(36).slice(2);

  const send = (content) => model.send(content);
  const select = (a, b) => {
    selected.clear();
    send({ kind: "select", a, b });
  };

  function entriesTable() {
    const a = model.get("a");
    const b = model.get("b");
    const rows = model.get("entries").map((entry) =>
      element(
        "tr",
        { class: entry.lineage ? "" : "qw-other" },
        element(
          "td",
          { class: "qw-pick" },
          element("input", {
            type: "radio",
            name: `a-${group}`,
            title: "Compare from this entry (A)",
            checked: entry.id === a,
            onchange: () => select(entry.id, model.get("b")),
          })
        ),
        element(
          "td",
          { class: "qw-pick" },
          element("input", {
            type: "radio",
            name: `b-${group}`,
            title: "Compare to this entry (B)",
            checked: entry.id === b,
            onchange: () => select(model.get("a"), entry.id),
          })
        ),
        element("td", { class: "qw-id" }, `#${entry.id}`),
        element("td", { class: "qw-time" }, entry.time),
        element(
          "td",
          { class: "qw-change", title: entry.parent === null ? "" : `after #${entry.parent}` },
          entry.change,
          entry.head ? element("span", { class: "qw-head" }, "current") : null
        ),
        element("td", { class: "qw-count" }, entry.leaves ? `${entry.leaves}` : "")
      )
    );
    return element(
      "div",
      { class: "qw-scroll" },
      element(
        "table",
        { class: "qw-table" },
        element(
          "thead",
          {},
          element(
            "tr",
            {},
            element("th", {}, "A"),
            element("th", {}, "B"),
            element("th", {}, "#"),
            element("th", {}, "time"),
            element("th", {}, "change"),
            element("th", { title: "changed leaves" }, "leaves")
          )
        ),
        element("tbody", {}, ...rows)
      )
    );
  }

  function diffTable() {
    const diff = model.get("diff");
    if (!diff.length) {
      return element("div", { class: "qw-empty" }, "No differences between A and B.");
    }
    const rows = diff.map((row) =>
      element(
        "tr",
        {},
        element(
          "td",
          { class: "qw-pick" },
          element("input", {
            type: "checkbox",
            title: "Select, to restore its value in A",
            checked: selected.has(row.path),
            onchange: (event) => {
              if (event.target.checked) selected.add(row.path);
              else selected.delete(row.path);
              draw();
            },
          })
        ),
        element("td", { class: "qw-path" }, row.path),
        element("td", { class: "qw-value", title: row.a_exact }, row.a),
        element("td", { class: "qw-value", title: row.b_exact }, row.b)
      )
    );
    return element(
      "div",
      { class: "qw-scroll" },
      element(
        "table",
        { class: "qw-table" },
        element(
          "thead",
          {},
          element(
            "tr",
            {},
            element("th", {}, ""),
            element("th", {}, "path"),
            element("th", {}, `A (#${model.get("a")})`),
            element("th", {}, `B (#${model.get("b")})`)
          )
        ),
        element("tbody", {}, ...rows)
      )
    );
  }

  function draw() {
    const a = model.get("a");
    const toolbar = element(
      "div",
      { class: "qw-toolbar" },
      element(
        "button",
        {
          class: "qw-button",
          title: "Restore the state of entry A, continuing from it",
          onclick: () => send({ kind: "restore", paths: null }),
        },
        `Restore #${a}`
      ),
      element(
        "button",
        {
          class: "qw-button",
          title: "Restore the selected paths as in entry A, on the current state",
          disabled: selected.size === 0,
          onclick: () => send({ kind: "restore", paths: [...selected] }),
        },
        `Restore ${selected.size} selected from #${a}`
      ),
      element(
        "button",
        {
          class: "qw-button",
          title: "Show the latest entries",
          onclick: () => send({ kind: "refresh" }),
        },
        "Refresh"
      )
    );
    const error = model.get("error");
    const snippet = model.get("snippet");
    root.replaceChildren(
      entriesTable(),
      toolbar,
      error ? element("div", { class: "qw-error" }, error) : null,
      snippet ? element("code", { class: "qw-snippet" }, snippet) : null,
      diffTable()
    );
  }

  for (const name of ["entries", "a", "b", "diff", "error", "snippet"]) {
    model.on(`change:${name}`, draw);
  }
  draw();
}

export default { render };
