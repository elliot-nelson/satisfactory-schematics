"""Load the building/segment catalog from ``config/buildings.yaml`` + ``segments.yaml``.

One list to rule them all -- every stage reads the catalog through here, so nothing can drift out of
sync (this replaced a pile of parallel ``.txt`` files that always did).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.cli.config import Config, ConfigError
from src.cli.context import REPO_ROOT


@dataclass(frozen=True)
class Building:
    name: str
    mesh: str
    blueprint: str
    category: str
    annot: dict[str, Any] | None = None


@dataclass(frozen=True)
class Segment:
    name: str
    mesh: str
    kind: str | None = None


@dataclass(frozen=True)
class Catalog:
    buildings: list[Building]
    segments: list[Segment]


def _load_yaml_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"catalog file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a YAML mapping at the top level")
    return data


def _resolve(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    return p if p.is_absolute() else REPO_ROOT / p


def load_catalog(cfg: Config) -> Catalog:
    """Parse both config files into a validated :class:`Catalog`."""
    buildings_raw = _load_yaml_map(_resolve(cfg.buildings))
    buildings: list[Building] = []
    for name, spec in buildings_raw.items():
        if not isinstance(spec, dict) or "mesh" not in spec or "blueprint" not in spec:
            raise ConfigError(f"buildings.yaml['{name}'] needs at least 'mesh' and 'blueprint'")
        buildings.append(
            Building(
                name=name,
                mesh=spec["mesh"],
                blueprint=spec["blueprint"],
                category=spec.get("category", "other"),
                annot=spec.get("annot"),
            )
        )

    segments: list[Segment] = []
    seg_path = _resolve(cfg.segments)
    if seg_path.exists():
        seg_raw = _load_yaml_map(seg_path)
        for name, spec in (seg_raw.get("segments") or {}).items():
            segments.append(Segment(name=name, mesh=spec["mesh"], kind=spec.get("kind")))

    return Catalog(buildings=buildings, segments=segments)
