"""Work out where the blueprint actually PLACES each building's body mesh.

We extract the raw mesh asset (its pivot at the origin), but the game attaches it via a component
carrying a RelativeLocation/RelativeRotation. Ports and clearance live in the blueprint-root frame,
so any building whose mesh component is offset/rotated renders misaligned unless we move it back.
This matches the component whose mesh == the body mesh we extracted and emits its transform in the
same building-local meters/blueprint frame as ports.json.

The optional ``annot`` correction (a small port-layer rotate/shift, e.g. the Particle Accelerator)
comes straight from the catalog (config/buildings.yaml) and is passed through here.

Output contract: ``{name: {loc:[x,y,z] m, pitch, yaw, roll, annot?}}``.
"""

from __future__ import annotations

from src.common.buildings import Catalog

from .util import body_mesh_leaf, mesh_leaf, name_by_asset_leaf, norm_deg

# Below these (meters / degrees) a transform is treated as identity.
EPS_M = 1e-3
EPS_DEG = 1e-2


def build_mesh_offsets(raw: list[dict], catalog: Catalog) -> tuple[dict[str, dict], list[str]]:
    """Return (offsets, notes). ``notes`` are human-readable per-building log lines."""
    by_leaf = name_by_asset_leaf(catalog)
    want = {b.name: body_mesh_leaf(b) for b in catalog.buildings}
    annot = {b.name: b.annot for b in catalog.buildings if b.annot}

    out: dict[str, dict] = {}
    notes: list[str] = []
    for entry in raw:
        leaf = entry["asset"].rsplit("/", 1)[-1]
        name = by_leaf.get(leaf)
        if name is None:
            continue
        target = want[name]
        comp = next(
            (c for c in entry.get("components", []) if mesh_leaf(c.get("mesh", "")) == target),
            None,
        )
        if comp is None:
            notes.append(f"[skip] {name}: no component uses mesh {target}")
            continue

        loc_m = [round(v / 100.0, 4) for v in comp["loc"]]
        pitch, yaw, roll = (round(norm_deg(v), 3) for v in comp["rot"])
        identity = (
            all(abs(v) < EPS_M for v in loc_m)
            and abs(pitch) < EPS_DEG
            and abs(yaw) < EPS_DEG
            and abs(roll) < EPS_DEG
        )
        has_annot = name in annot
        if identity and not has_annot:
            notes.append(f"[ok] {name}: identity (no offset needed)")
            continue

        rec: dict = {"loc": loc_m, "pitch": pitch, "yaw": yaw, "roll": roll}
        if has_annot:
            rec["annot"] = annot[name]
            notes.append(f"[corr] {name}: annot={annot[name]}")
        notes.append(f"[ok] {name}: loc={loc_m} yaw={yaw} pitch={pitch} roll={roll}")
        out[name] = rec
    return out, notes
