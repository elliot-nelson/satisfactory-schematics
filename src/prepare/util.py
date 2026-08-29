"""Shared helpers for the prepare stage: catalog-derived name maps + small math/string utils."""

from __future__ import annotations

from src.common.buildings import Building, Catalog


def blueprint_leaf(building: Building) -> str:
    """'.../Build_ConstructorMk1' -> 'Build_ConstructorMk1' (matches the raw dump's asset leaf)."""
    return building.blueprint.rstrip("/").rsplit("/", 1)[-1]


def body_mesh_leaf(building: Building) -> str:
    """'.../Mesh/ConstructorMk1_static' -> 'ConstructorMk1_static' (the mesh we extracted)."""
    return building.mesh.rstrip("/").rsplit("/", 1)[-1]


def clearance_class(building: Building) -> str:
    """Docs CDO ClassName, e.g. 'Build_ConstructorMk1' -> 'Build_ConstructorMk1_C'."""
    return blueprint_leaf(building) + "_C"


def name_by_asset_leaf(catalog: Catalog) -> dict[str, str]:
    """{blueprint leaf -> friendly building name} to resolve each raw ports.raw.json entry."""
    return {blueprint_leaf(b): b.name for b in catalog.buildings}


def mesh_leaf(ref: str) -> str:
    """ "StaticMesh'/Game/.../SM_X.SM_X'" -> 'SM_X'.  '' -> ''."""
    if not ref:
        return ""
    if "'" in ref:
        parts = ref.split("'")
        ref = parts[1] if len(parts) > 1 else ref
    ref = ref.rsplit("/", 1)[-1]  # drop package path
    return ref.rsplit(".", 1)[-1]  # drop the .ObjectName suffix


def norm_deg(d: float) -> float:
    """Wrap degrees to (-180, 180]."""
    d = ((d + 180.0) % 360.0) - 180.0
    return 180.0 if d == -180.0 else d
