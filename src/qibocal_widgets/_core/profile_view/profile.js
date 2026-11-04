// Title line of an execution, with its profile folded: a toggle, the steps,
// and buttons copying them as Markdown or CSV. Plain ES module for anywidget.

function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(name, value);
  }
  for (const child of children) {
    if (child !== null && child !== undefined && child !== false) {
      node.append(typeof child === "string" ? document.createTextNode(child) : child);
    }
  }
  return node;
}

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // insecure contexts: a temporary selection
    const area = element("textarea", { class: "qw-hidden" });
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const label = button.textContent;
  button.textContent = "copied";
  setTimeout(() => (button.textContent = label), 900);
}

function render({ model, el }) {
  const root = element("div", { class: "qw-title" });
  el.append(root);

  function draw() {
    const steps = model.get("steps");
    const unfolded = model.get("unfolded");
    const line = element(
      "div",
      { class: "qw-line" },
      element("span", { class: "qw-name" }, model.get("title")),
      model.get("times") ? element("span", { class: "qw-times" }, model.get("times")) : null,
      steps.length
        ? element(
            "button",
            {
              class: `qw-toggle${unfolded ? " qw-on" : ""}`,
              title: "Where the time went, step by step",
              "aria-expanded": String(unfolded),
              onclick: () => {
                model.set("unfolded", !unfolded);
                model.save_changes();
              },
            },
            `⏱ profile ${unfolded ? "▾" : "▸"}`
          )
        : null
    );
    const parts = [line];
    if (unfolded && steps.length) {
      const total = steps.reduce((sum, s) => sum + s.took, 0);
      const rows = steps.map((s) =>
        element(
          "tr",
          { class: total > 0 && s.took >= 0.25 * total ? "qw-long" : "" },
          element("td", {}, s.step),
          element("td", { class: "qw-number" }, s.took.toFixed(3)),
          element("td", { class: "qw-number" }, s.at.toFixed(3))
        )
      );
      const markdown = element("button", { class: "qw-copy", title: "A Markdown table with the context, for issues", onclick: () => copy(model.get("markdown"), markdown) }, "Copy");
      const csv = element("button", { class: "qw-copy", title: "CSV, with the context as comments", onclick: () => copy(model.get("csv"), csv) }, "CSV");
      parts.push(
        element(
          "div",
          { class: "qw-panel" },
          element(
            "table",
            {},
            element("thead", {}, element("tr", {}, element("th", {}, "step"), element("th", {}, "took (s)"), element("th", {}, "at (s)"))),
            element("tbody", {}, ...rows)
          ),
          element("div", { class: "qw-actions" }, markdown, csv)
        )
      );
    }
    root.replaceChildren(...parts);
  }

  for (const name of ["steps", "unfolded", "title", "times"]) model.on(`change:${name}`, draw);
  draw();
}

export default { render };
