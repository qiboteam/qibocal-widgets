"""The public modules only re-export objects implemented in ``_core``."""

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import qibocal_widgets

PACKAGE = Path(qibocal_widgets.__file__).parent
PUBLIC = sorted(
    p for p in PACKAGE.rglob("*.py") if "_core" not in p.relative_to(PACKAGE).parts
)


def _module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


@pytest.mark.parametrize("path", PUBLIC, ids=lambda p: p.name)
def test_only_reexports(path):
    """Besides the docstring, only imports and ``__all__`` are allowed."""
    tree = ast.parse(path.read_text())
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
    ):
        body = body[1:]
    for node in body:
        if isinstance(node, ast.ImportFrom):
            assert node.level > 0 and node.module.startswith("_core"), ast.unparse(node)
        elif isinstance(node, ast.Assign):
            assert [ast.unparse(t) for t in node.targets] == ["__all__"]
        else:
            pytest.fail(f"{path.name}: unexpected statement {ast.unparse(node)}")


@pytest.mark.parametrize("path", PUBLIC, ids=lambda p: p.name)
def test_all_is_consistent(path):
    name = _module_name(path)
    frontend = {"marimo": "marimo", "jupyter": "ipywidgets"}.get(name.split(".")[-1])
    if frontend is not None:
        pytest.importorskip(frontend)
    module = importlib.import_module(name)
    exported = {
        n
        for n, obj in vars(module).items()
        if not n.startswith("_") and not inspect.ismodule(obj)
    }
    # everything public is declared, and everything declared exists
    assert exported <= set(module.__all__)
    assert set(module.__all__) <= set(vars(module))
    for attribute in module.__all__:
        obj = getattr(module, attribute)
        if inspect.isclass(obj) or inspect.isfunction(obj):
            assert obj.__module__.startswith("qibocal_widgets._core.")
