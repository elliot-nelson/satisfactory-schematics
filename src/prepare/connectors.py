"""Map buildings -> the shared belt/pipe MOUTH-plate meshes they attach, and at what transform.

Compact machines model their mouths into the body, but some (notably the Particle Accelerator)
attach small shared FactoryInputs plates several meters out. With only the body rendered the port
markers float in empty space; rendering these plates at their blueprint transform puts them back on
visible geometry. We keep components whose mesh lives under FactoryInputs/Mesh and whose ``.glb``
was actually extracted (into ``build/01-extract/models/connectors/``).

Transforms are in the blueprint-root frame (same as ports.json), NOT the body's mesh_offsets frame.

Output contract: ``{name: [{mesh, loc:[x,y,z] m, yaw, pitch, roll}]}``.
"""

from __future__ import annotations

from pathlib import Path

from src.common.buildings import Catalog

from .util import mesh_leaf, name_by_asset_leaf, norm_deg

# A connector mesh is one of the shared FactoryInputs plates; match on path so new variants
# (SM_Input_02, ...) are picked up automatically as long as their .glb exists.
CONNECTOR_PATH_HINT = "FactoryInputs/Mesh"


def build_connectors(
    raw: list[dict], catalog: Catalog, connectors_dir: Path
) -> tuple[dict[str, list[dict]], list[str]]:
    """Return (placements, notes)."""
    by_leaf = name_by_asset_leaf(catalog)
    out: dict[str, list[dict]] = {}
    notes: list[str] = []
    for entry in raw:
        leaf = entry["asset"].rsplit("/", 1)[-1]
        name = by_leaf.get(leaf)
        if name is None:
            continue
        placements: list[dict] = []
        for c in entry.get("components", []):
            ref = c.get("mesh", "")
            if CONNECTOR_PATH_HINT not in ref:
                continue
            stem = mesh_leaf(ref)
            if not (connectors_dir / f"{stem}.glb").is_file():
                notes.append(f"[warn] {name}: references {stem} but its .glb is missing")
                continue
            pitch, yaw, roll = (round(norm_deg(v), 3) for v in c["rot"])
            placements.append(
                {
                    "mesh": stem,
                    "loc": [round(v / 100.0, 4) for v in c["loc"]],
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                }
            )
        if placements:
            out[name] = placements
            meshes = ", ".join(p["mesh"] for p in placements)
            notes.append(f"[ok] {name}: {len(placements)} connector(s): {meshes}")
    return out, notes
