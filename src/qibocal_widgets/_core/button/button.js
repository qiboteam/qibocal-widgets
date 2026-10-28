function render({ model, el }) {
  const button = document.createElement("button");
  button.className = "qw-run";
  const sync = () => {
    button.textContent = model.get("label");
    button.title = model.get("tooltip");
    button.disabled = model.get("disabled");
  };
  sync();
  model.on("change", sync);
  button.addEventListener("click", () => {
    button.disabled = true;
    model.send({ event: "click" });
  });
  el.appendChild(button);
}

export default { render };
