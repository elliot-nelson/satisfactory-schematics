"""Pull each buildable's true in-game clearance box out of the game's docs dump.

The clearance box is the "allowed space" a building occupies on the world grid -- NOT its visible
mesh (a Constructor's legs are narrower than its 8x10 m footprint; an Assembler needs 1 extra meter
its geometry never touches). We take the UNION of all HARD (non ``CT_Soft``) clearance boxes,
falling back to every box when a building has only soft boxes (splitters/mergers).
``ExcludeForSnapping`` boxes are still counted -- "foundations may snap under this overhang", not
"empty space".

Each entry's 8 local box corners are transformed by Scale3D -> Rotation(conjugate) -> Translation,
then reduced to axis-aligned world bounds (cm -> m). The stored rotation is parent<-local, so it
must be inverted; applying it directly puts rotated arm segments (Particle Accelerator) far into
empty space. See SPEC.md / the old build_clearance.py for the full validation notes.

Output contract: ``{name: {min:[x,y,z] m, max:[x,y,z] m}}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.common.buildings import Catalog
from src.common.plan import StageError

from .util import clearance_class

_BOX_RE = re.compile(
    r"ClearanceBox=\(Min=\(X=(-?[\d.]+),Y=(-?[\d.]+),Z=(-?[\d.]+)\),"
    r"Max=\(X=(-?[\d.]+),Y=(-?[\d.]+),Z=(-?[\d.]+)\)"
)
_TRANS_RE = re.compile(
    r"RelativeTransform=\(Translation=\(X=(-?[\d.]+),Y=(-?[\d.]+),Z=(-?[\d.]+)\)"
)
_ROT_RE = re.compile(r"Rotation=\(X=(-?[\d.eE]+),Y=(-?[\d.eE]+),Z=(-?[\d.eE]+),W=(-?[\d.eE]+)\)")
_SCALE_RE = re.compile(r"Scale3D=\(X=(-?[\d.eE]+),Y=(-?[\d.eE]+),Z=(-?[\d.eE]+)\)")


def _cross(a: tuple, b: tuple) -> tuple:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _rotate_conj(q: list[float], v: tuple) -> tuple:
    """Rotate v by the CONJUGATE of quaternion q=(x,y,z,w)."""
    qx = (-q[0], -q[1], -q[2])
    w = q[3]
    t = _cross(qx, v)
    t = (2 * t[0], 2 * t[1], 2 * t[2])
    c = _cross(qx, t)
    return (v[0] + w * t[0] + c[0], v[1] + w * t[1] + c[1], v[2] + w * t[2] + c[2])


def read_docs(path: Path) -> object:
    """Docs/*.json is UTF-16; fall back through a couple of encodings just in case."""
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise StageError(f"could not decode {path} as UTF-16/UTF-8")


def find_class(docs: object, class_name: str) -> dict | None:
    """Depth-first search for the CDO dict whose ClassName matches and carries clearance data."""
    stack = [docs]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("ClassName") == class_name and node.get("mClearanceData"):
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _split_entries(clearance_str: str) -> list[str]:
    """Split the mClearanceData array string into its top-level ``(...)`` entries."""
    inner = clearance_str.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    entries, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            entries.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        entries.append(cur)
    return entries


def _entry_box_m(entry: str) -> tuple[list[float], list[float]] | None:
    """Origin-relative (min, max) box in METERS for one clearance entry, or None."""
    m = _BOX_RE.search(entry)
    if not m:
        return None
    vals = [float(x) for x in m.groups()]
    lmn, lmx = vals[0:3], vals[3:6]
    t = _TRANS_RE.search(entry)
    tx = [float(x) for x in t.groups()] if t else [0.0, 0.0, 0.0]
    r = _ROT_RE.search(entry)
    q = [float(x) for x in r.groups()] if r else [0.0, 0.0, 0.0, 1.0]
    s = _SCALE_RE.search(entry)
    sc = [float(x) for x in s.groups()] if s else [1.0, 1.0, 1.0]

    pts = []
    for cx in (lmn[0], lmx[0]):
        for cy in (lmn[1], lmx[1]):
            for cz in (lmn[2], lmx[2]):
                v = _rotate_conj(q, (cx * sc[0], cy * sc[1], cz * sc[2]))
                pts.append((v[0] + tx[0], v[1] + tx[1], v[2] + tx[2]))
    mn = [min(p[i] for p in pts) / 100.0 for i in range(3)]
    mx = [max(p[i] for p in pts) / 100.0 for i in range(3)]
    return mn, mx


def _union_box_m(clearance_str: str) -> dict | None:
    """Origin-relative box (m): union of all HARD boxes (or every box if none are hard)."""
    hard, everything = [], []
    for entry in _split_entries(clearance_str):
        box = _entry_box_m(entry)
        if box is None:
            continue
        everything.append(box)
        if "CT_Soft" not in entry:
            hard.append(box)
    boxes = hard or everything
    if not boxes:
        return None
    mn = [min(b[0][i] for b in boxes) for i in range(3)]
    mx = [max(b[1][i] for b in boxes) for i in range(3)]
    return {"min": [round(v, 4) for v in mn], "max": [round(v, 4) for v in mx]}


def build_clearance(docs: object, catalog: Catalog) -> tuple[dict[str, dict], list[str]]:
    """Return (clearance, notes)."""
    out: dict[str, dict] = {}
    notes: list[str] = []
    for b in catalog.buildings:
        cls = clearance_class(b)
        node = find_class(docs, cls)
        if not node:
            notes.append(f"[skip] {b.name}: {cls} not found in docs")
            continue
        box = _union_box_m(node["mClearanceData"])
        if not box:
            notes.append(f"[skip] {b.name}: no clearance box")
            continue
        dx, dy, dz = (box["max"][i] - box["min"][i] for i in range(3))
        out[b.name] = box
        notes.append(f"[ok] {b.name}: {dx:.1f} x {dy:.1f} x {dz:.1f} m")
    return out, notes
