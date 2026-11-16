"""Stable UUIDs shared by the schematic and board generators, so that every footprint
points at its schematic symbol (KiCad's "update PCB from schematic" then just works)."""
import uuid

_NS = uuid.UUID("6f3c1f5e-fe7a-4c0e-9a51-0000fe7ac07e")
PROJECT = "fera-core"


def uid(*key):
    return str(uuid.uuid5(_NS, "/".join(str(k) for k in key)))


ROOT = uid("root-sheet")


def sheet(section):
    return uid("sheet", section)


def symbol(ref):
    return uid("symbol", ref)


def symbol_path(section, ref):
    return f"/{sheet(section)}/{symbol(ref)}"
