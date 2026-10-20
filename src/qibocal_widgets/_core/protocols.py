"""Identification of protocol objects by name."""

from __future__ import annotations

import importlib

from qibocal.auto.operation import Protocol

__all__ = ["PROTOCOLS", "reference", "registered_name"]

PROTOCOLS = "qibocal.protocols"
"""Module of the built-in protocols."""


def _find(module_name: str | None, protocol: Protocol) -> str | None:
    if module_name is None or module_name == "__main__":
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    for attribute, value in vars(module).items():
        if value is protocol:
            return attribute
    return None


def registered_name(protocol: Protocol) -> str | None:
    """Name of a protocol among the built-in ones, if registered.

    Only registered protocols can be loaded back by Qibocal (e.g. from the
    ``action.yml`` of an output folder).
    """
    return _find(PROTOCOLS, protocol)


def reference(protocol: Protocol) -> str | None:
    """Importable ``module:attribute`` reference of a protocol, if any.

    Built-in protocols are found in :mod:`qibocal.protocols`, others in the
    module defining their acquisition function. Protocols defined in a
    notebook cell, or not at the top level of their module, have none.
    """
    name = registered_name(protocol)
    if name is not None:
        return f"{PROTOCOLS}:{name}"
    module = getattr(protocol.acquisition, "__module__", None)
    attribute = _find(module, protocol)
    return f"{module}:{attribute}" if attribute is not None else None
