// Platform state explorer: renders rows computed in Python, and sends back
// navigation and edit requests. No build step: plain ES module for anywidget.

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

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // insecure contexts: fall back to a temporary selection
    const area = element("textarea", { class: "qw-hidden" });
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  if (button) {
    const label = button.textContent;
    button.textContent = "copied";
    setTimeout(() => (button.textContent = label), 900);
  }
}

function render({ model, el }) {
  const root = element("div", { class: "qw-explorer" });
  el.append(root);

  const send = (content) => model.send(content);

  const input = element("input", {
    class: "qw-nav",
    type: "text",
    spellcheck: "false",
    placeholder: "path, pasted code, or search…",
    onkeydown: (event) => {
      if (event.key === "Enter") send({ kind: "navigate", text: input.value });
      if (event.key === "Escape") input.value = model.get("query") || model.get("path");
    },
  });
  const up = element("button", {
    class: "qw-button",
    title: "Parent",
    onclick: () => {
      const path = model.get("path");
      send({ kind: "navigate", text: path.includes(".") ? path.slice(0, path.lastIndexOf(".")) : "" });
    },
  }, "↑");
  const reload = element("button", {
    class: "qw-button",
    title: "Reload the current state",
    onclick: () => send({ kind: "refresh" }),
  }, "⟳");
  const changedOnly = element("input", {
    type: "checkbox",
    onchange: () => {
      model.set("changed_only", changedOnly.checked);
      model.save_changes();
    },
  });
  const changedLabel = element("label", { class: "qw-option" }, changedOnly, " changed only");
  const bar = element("div", { class: "qw-bar" }, up, input, reload, changedLabel);

  const crumbs = element("div", { class: "qw-crumbs" });
  const table = element("table", { class: "qw-table" });
  const footer = element("div", { class: "qw-footer" });
  root.append(bar, crumbs, table, footer);

  function startEdit(cell, row) {
    const field = element("input", { class: "qw-edit", type: "text", spellcheck: "false" });
    field.value = row.raw;
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") send({ kind: "edit", path: row.path, value: field.value });
      if (event.key === "Escape") draw();
    });
    cell.replaceChildren(field);
    field.focus();
    field.select();
  }

  function drawRow(row) {
    const key =
      row.kind === "branch"
        ? element("a", { class: "qw-branch", onclick: () => send({ kind: "navigate", text: row.path }) }, "▸ " + row.key)
        : element("span", { class: "qw-key" }, row.key);
    const value = element("td", { class: "qw-value", title: row.raw || row.path }, row.display);
    if (row.changed && row.before) {
      value.append(element("span", { class: "qw-before", title: "Value in the compared state" }, " was " + row.before));
    }
    const pathButton = element("button", { class: "qw-button", title: "Copy path: " + row.path }, "path");
    pathButton.addEventListener("click", () => copy(row.path, pathButton));
    const actions = element("td", { class: "qw-actions" }, pathButton);
    if (row.kind === "leaf") {
      const valueButton = element("button", { class: "qw-button", title: "Copy value: " + row.raw }, "value");
      valueButton.addEventListener("click", () => copy(row.raw, valueButton));
      actions.append(valueButton);
      if (model.get("editable")) {
        actions.append(element("button", { class: "qw-button", title: "Edit", onclick: () => startEdit(value, row) }, "edit"));
      }
    }
    return element("tr", { class: row.changed ? "qw-changed" : "" }, element("td", { class: "qw-name" }, key), value, actions);
  }

  function draw() {
    const query = model.get("query");
    if (document.activeElement !== input) input.value = query || model.get("path");
    changedLabel.style.display = model.get("comparing") ? "" : "none";
    changedOnly.checked = model.get("changed_only");

    crumbs.replaceChildren();
    if (query) {
      crumbs.append(element("span", { class: "qw-search" }, `search “${query}”`));
    } else {
      model.get("crumbs").forEach((crumb, index) => {
        if (index > 0) crumbs.append(" › ");
        crumbs.append(element("a", { onclick: () => send({ kind: "navigate", text: crumb.path }) }, crumb.label));
      });
    }

    const rows = model.get("rows");
    table.replaceChildren(...rows.map(drawRow));
    if (rows.length === 0) table.append(element("tr", {}, element("td", { class: "qw-empty" }, "nothing here")));

    footer.replaceChildren();
    const error = model.get("error");
    if (error) footer.append(element("div", { class: "qw-error" }, error));
    const snippet = model.get("snippet");
    if (snippet) {
      const button = element("button", { class: "qw-button", title: "Copy code" }, "copy");
      button.addEventListener("click", () => copy(snippet, button));
      footer.append(element("div", { class: "qw-snippet" }, element("code", {}, snippet), button));
    }
  }

  for (const name of ["rows", "crumbs", "query", "path", "error", "snippet", "editable", "comparing", "changed_only"]) {
    model.on(`change:${name}`, draw);
  }
  draw();
}

export default { render };
