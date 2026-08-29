"""Prepare stage: read ``build/01-extract/`` and write the four JSON files the renderer needs into
``build/02-prepare/``. Pure Python, offline, and always whole-catalog -- it ignores ``--only`` since
these files are tiny and we want them complete for the renderer."""

from __future__ import annotations

import json
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import EXTRACT_DIR, PREPARE_DIR, REPO_ROOT, ensure
from src.common.buildings import load_catalog
from src.common.plan import BuildPlan, StageError

from .clearance import build_clearance, read_docs
from .connectors import build_connectors
from .mesh_offsets import build_mesh_offsets
from .ports import build_ports
from .util import name_by_asset_leaf

RAW_PORTS = EXTRACT_DIR / "ports.raw.json"
DOCS = EXTRACT_DIR / "docs" / "en-US.json"
CONNECTORS_DIR = EXTRACT_DIR / "models" / "connectors"


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _summary(kind: str, count: int, notes: list[str]) -> None:
    for line in notes:
        C.console.print(f"  [dim]{line}[/]")
    C.console.print(f"  [green]{kind}[/]: {count} entr{'y' if count == 1 else 'ies'}")


def run(cfg: Config, plan: BuildPlan) -> None:
    """Turn the extract outputs into clearance/ports/mesh_offsets/connectors JSON.

    We take ``plan`` just to match the stage signature -- prepare is cheap and whole-catalog, so it
    ignores ``--only`` and always writes the complete set.
    """
    del plan
    catalog = load_catalog(cfg)
    ensure(PREPARE_DIR)

    if not RAW_PORTS.is_file():
        raise StageError(f"{_rel(RAW_PORTS)} not found. Run `./schematic extract` first.")
    raw = json.loads(RAW_PORTS.read_text(encoding="utf-8"))
    name_by_leaf = name_by_asset_leaf(catalog)

    # ports.json
    ports = build_ports(raw, name_by_leaf)
    _write_json(PREPARE_DIR / "ports.json", ports)
    n_ports = sum(len(v) for v in ports.values())
    C.console.print(f"  [green]ports[/]: {n_ports} across {len(ports)} building(s)")

    # mesh_offsets.json
    offsets, off_notes = build_mesh_offsets(raw, catalog)
    _write_json(PREPARE_DIR / "mesh_offsets.json", offsets)
    _summary("mesh_offsets", len(offsets), off_notes)

    # connectors.json
    connectors, con_notes = build_connectors(raw, catalog, CONNECTORS_DIR)
    _write_json(PREPARE_DIR / "connectors.json", connectors)
    _summary("connectors", len(connectors), con_notes)

    # clearance.json (needs the docs dump; graceful skip if extract hasn't copied it yet)
    if DOCS.is_file():
        clearance, clr_notes = build_clearance(read_docs(DOCS), catalog)
        _write_json(PREPARE_DIR / "clearance.json", clearance)
        _summary("clearance", len(clearance), clr_notes)
    else:
        C.err_console.print(
            f"  [yellow]clearance skipped[/]: {_rel(DOCS)} missing "
            "(re-run `./schematic extract` to copy the game docs)."
        )

    C.console.print(f"\n[green]Prepare complete[/] -> {_rel(PREPARE_DIR)}")
