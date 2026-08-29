"""Runs INSIDE Blender: ``blender -b -P entry.py -- <args>``.

For one building ``.glb`` this produces, theme-independently:
  * per-view **true-to-scale orthographic alpha-silhouette rasters** (EEVEE over a transparent
    film) into ``--outdir``,
  * per-view **Freestyle feature-edge strokes** (``<name>_<view>.paths``) into ``--strokes-dir``
    -- colorless polylines the finalize stage stitches + colors per theme, and
  * a **projection manifest** ``<name>.json`` into ``--manifest-dir`` -- the important one: per view
    it carries the pixel geometry finalize/annotate/preview need: grid cells, the clearance-box
    pixel rect (``clearance_px``) and the projected I/O-port pixel rects (``ports_px``).

To get those pixels right we first drop the mesh into the same blueprint-root frame that ports.json
/ clearance.json use: apply the mesh offset, draw any attached connector mouth-plates, apply the
per-building ``annot`` fixup, then canonicalize flow-through machines (OUTPUT=+Y / INPUT=-Y). Ported
from the old standalone ``render.py``. Turning all this into the final SVG (traced fill + stitched
strokes + overlays) is the separate pure-Python finalize phase; this stage stops at the
theme-independent raster + strokes + manifest.

Self-contained: imports only bpy / mathutils / stdlib (Blender runs it in its own interpreter).
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

HALF_PI = math.pi / 2
PI = math.pi

# Which world axes map to the image's horizontal/vertical, plus the camera orientation and the unit
# offset direction it sits along. front/back and left/right are swapped vs the raw Blender axes so
# the labels line up with Satisfactory's own input/output convention.
VIEWS = {
    "top":   {"euler": (0.0,     0.0,  0.0),     "offset": (0, 0, 1),  "h": "x", "v": "y"},
    "front": {"euler": (HALF_PI, 0.0,  PI),      "offset": (0, 1, 0),  "h": "x", "v": "z"},
    "back":  {"euler": (HALF_PI, 0.0,  0.0),     "offset": (0, -1, 0), "h": "x", "v": "z"},
    "right": {"euler": (HALF_PI, 0.0, -HALF_PI), "offset": (-1, 0, 0), "h": "y", "v": "z"},
    "left":  {"euler": (HALF_PI, 0.0,  HALF_PI), "offset": (1, 0, 0),  "h": "y", "v": "z"},
}  # fmt: skip

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def parse_args(argv):
    p = argparse.ArgumentParser(description="Orthographic raster + projection manifest.")
    p.add_argument("--input", required=True, help="Path to a .glb / .gltf.")
    p.add_argument("--outdir", required=True, help="Directory for <name>_<view>.png rasters.")
    p.add_argument(
        "--strokes-dir", required=True, help="Directory for <name>_<view>.paths strokes."
    )
    p.add_argument("--manifest-dir", required=True, help="Directory for the <name>.json manifest.")
    p.add_argument("--name", required=True, help="Output stem (building key).")
    p.add_argument(
        "--crease-deg", type=float, default=70.0, help="Only capture creases sharper than this."
    )
    p.add_argument("--views", default="top,front,back,left,right", help="Comma-separated views.")
    p.add_argument("--ppm", type=float, default=20.0, help="Pixels per meter.")
    p.add_argument("--grid", type=float, default=1.0, help="Grid-snap cell size in meters (0=off).")
    p.add_argument("--meters-per-unit", type=float, default=1.0, help="glTF is already meters.")
    p.add_argument(
        "--bbox-gap",
        type=float,
        default=2.0,
        help="Drop stray geometry separated by a gap larger than this (m). 0=off.",
    )
    # prepare-stage files (all optional -- if one's missing we just carry on without it)
    p.add_argument("--clearance", default=None, help="clearance.json (in-game footprint boxes).")
    p.add_argument("--ports", default=None, help="ports.json (belt/pipe I/O).")
    p.add_argument("--mesh-offsets", default=None, help="mesh_offsets.json (blueprint placement).")
    p.add_argument("--connectors", default=None, help="connectors.json (attached mouth plates).")
    p.add_argument("--connectors-dir", default=None, help="Folder of connector .glb files.")
    p.add_argument("--no-canonical", action="store_true", help="Skip OUTPUT=+Y/INPUT=-Y rotation.")
    p.add_argument("--no-port-snap", action="store_true", help="Keep ports at the raw point.")
    # port-marker geometry (meters); see render.py --port-* for the rationale
    p.add_argument("--port-size", type=float, default=2.0)
    p.add_argument("--port-belt-size", type=float, default=2.0)
    p.add_argument("--port-pipe-size", type=float, default=1.2)
    p.add_argument("--port-drop", type=float, default=0.2)
    return p.parse_args(argv)


# --------------------------------------------------------------------------------------------------
# scene / import
# --------------------------------------------------------------------------------------------------
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            block.remove(item)


def import_model(path):
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def import_extra(path):
    """Import another .glb and return ONLY the objects it added (for shared connector meshes)."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o not in before]


# --------------------------------------------------------------------------------------------------
# bounding boxes
# --------------------------------------------------------------------------------------------------
def world_bbox(mesh_objects):
    mins = Vector((math.inf, math.inf, math.inf))
    maxs = Vector((-math.inf, -math.inf, -math.inf))
    for obj in mesh_objects:
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    return mins, maxs


def _robust_extent(vals_sorted, gap, max_trim):
    """(lo, hi) after peeling DISCONNECTED outliers across an empty span larger than `gap`."""
    n = len(vals_sorted)
    hi = n - 1
    for i in range(n - 1, max(0, n - max_trim) - 1, -1):
        if i > 0 and vals_sorted[i] - vals_sorted[i - 1] > gap:
            hi = i - 1
            break
    lo = 0
    for i in range(0, min(n - 1, max_trim)):
        if vals_sorted[i + 1] - vals_sorted[i] > gap:
            lo = i + 1
            break
    return vals_sorted[lo], vals_sorted[hi]


def robust_world_bbox(mesh_objects, gap_bu, max_trim_frac=0.02):
    """Vertex-level world bbox that ignores disconnected stray geometry. gap_bu<=0 -> plain bbox."""
    if gap_bu <= 0:
        return world_bbox(mesh_objects)
    cols = ([], [], [])
    for obj in mesh_objects:
        mw = obj.matrix_world
        for v in obj.data.vertices:
            w = mw @ v.co
            cols[0].append(w.x)
            cols[1].append(w.y)
            cols[2].append(w.z)
    if not cols[0]:
        return world_bbox(mesh_objects)
    mins, maxs = Vector((0, 0, 0)), Vector((0, 0, 0))
    max_trim = max(8, int(len(cols[0]) * max_trim_frac))
    for i in range(3):
        cols[i].sort()
        mins[i], maxs[i] = _robust_extent(cols[i], gap_bu, max_trim)
    return mins, maxs


# --------------------------------------------------------------------------------------------------
# prepare-data loaders (blueprint -> Blender frame: glTF export negates Y, so we mirror Y here too)
# --------------------------------------------------------------------------------------------------
def _load_map(path, name):
    if not path or not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get(name)
    except (OSError, ValueError):
        return None


def load_ports(path, name, mpu):
    """[{role, kind, pos:Vector(bu), face:Vector}] in the Blender frame (Y mirrored), or []."""
    entry = _load_map(path, name)
    if not entry:
        return []
    inv = 1.0 / mpu
    out = []
    for p in entry:
        yaw = math.radians(p.get("yaw", 0.0))
        px, py, pz = p["pos"]
        out.append(
            {
                "role": p["role"],
                "kind": p.get("kind", "belt"),
                "pos": Vector((px, -py, pz)) * inv,
                "face": Vector((math.cos(yaw), -math.sin(yaw), 0.0)),
            }
        )
    return out


def load_clearance(path, name):
    """{'min':Vector, 'max':Vector} meters in the Blender frame (Y mirrored), or None."""
    box = _load_map(path, name)
    if not box or "min" not in box or "max" not in box:
        return None
    mn, mx = box["min"], box["max"]
    return {"min": Vector((mn[0], -mx[1], mn[2])), "max": Vector((mx[0], -mn[1], mx[2]))}


# --------------------------------------------------------------------------------------------------
# orientation: mesh offset -> connectors -> annot correction -> canonical yaw
# --------------------------------------------------------------------------------------------------
def apply_mesh_offset(mesh_objects, offset, inv):
    """Move the imported mesh into the blueprint-root frame (rotate about Z by -yaw, then translate
    (Tx, -Ty, Tz)); the Y sign flips because Blender's frame is Unreal's with Y negated."""
    if not offset:
        return
    loc = offset.get("loc", [0.0, 0.0, 0.0])
    yaw = float(offset.get("yaw", 0.0))
    pitch, roll = float(offset.get("pitch", 0.0)), float(offset.get("roll", 0.0))
    if abs(pitch) > 0.01 or abs(roll) > 0.01:
        print(
            f"  WARNING: mesh offset has pitch={pitch:.2f} roll={roll:.2f} (only yaw applied)",
            file=sys.stderr,
        )
    m = Matrix.Translation((loc[0] * inv, -loc[1] * inv, loc[2] * inv)) @ Matrix.Rotation(
        math.radians(-yaw), 4, "Z"
    )
    for obj in mesh_objects:
        obj.matrix_world = m @ obj.matrix_world
    bpy.context.view_layer.update()


def load_connectors(path, name):
    return _load_map(path, name) or []


def place_connectors(placements, connectors_dir, inv):
    """Import each connector mouth mesh and move it into the blueprint-root frame (same math as the
    body offset). Returns the imported objects so the caller can fold them into the model."""
    added = []
    for pl in placements:
        glb = Path(connectors_dir) / f"{pl['mesh']}.glb"
        if not glb.is_file():
            print(f"  WARNING: connector mesh missing: {glb} (skipped)", file=sys.stderr)
            continue
        objs = import_extra(str(glb))
        apply_mesh_offset(objs, pl, inv)
        added.extend(objs)
    return added


def apply_annot_offset(annot, ports, conn_objs, body_center, inv):
    """Rotate/shift the ANNOTATION layer (ports + connector meshes) about the body's vertical axis
    to seat it on the body, for buildings whose extracted port frame is out of sync (Particle
    Accelerator). Driven by the catalog's optional ``annot`` block."""
    if not annot:
        return
    rot_deg = float(annot.get("rot_deg", 0.0))
    shift = annot.get("shift", [0.0, 0.0, 0.0])
    cx, cy = body_center
    m = (
        Matrix.Translation((cx + shift[0] * inv, cy + shift[1] * inv, shift[2] * inv))
        @ Matrix.Rotation(math.radians(rot_deg), 4, "Z")
        @ Matrix.Translation((-cx, -cy, 0.0))
    )
    r3 = m.to_3x3()
    for p in ports:
        p["pos"] = m @ p["pos"]
        p["face"] = (r3 @ p["face"]).normalized()
    for o in conn_objs:
        o.matrix_world = m @ o.matrix_world
    if conn_objs:
        bpy.context.view_layer.update()


def canonical_yaw(ports):
    """Z rotation (deg, multiple of 90) that puts OUTPUTS on +Y and INPUTS on -Y, or None if the
    building isn't a flow-through machine (junctions have I/O on three sides -> leave as-is)."""
    ins = [p for p in ports if p["role"] == "input"]
    outs = [p for p in ports if p["role"] == "output"]
    if not ins or not outs:
        return None

    def one_facing(group):
        keys = {(round(p["face"].x), round(p["face"].y), round(p["face"].z)) for p in group}
        return next(iter(keys)) if len(keys) == 1 else None

    fin, fout = one_facing(ins), one_facing(outs)
    if fin is None or fout is None:
        return None
    if (round(fin[0]), round(fin[1])) != (-round(fout[0]), -round(fout[1])):
        return None
    of = outs[0]["face"]
    theta = math.degrees(HALF_PI - math.atan2(of.y, of.x))
    theta = round(theta / 90.0) * 90.0
    return ((theta + 180.0) % 360.0) - 180.0


def _rotate_box_z(box, rot):
    mn, mx = box["min"], box["max"]
    xs, ys = [], []
    for cx in (mn.x, mx.x):
        for cy in (mn.y, mx.y):
            w = rot @ Vector((cx, cy, 0.0))
            xs.append(w.x)
            ys.append(w.y)
    return {"min": Vector((min(xs), min(ys), mn.z)), "max": Vector((max(xs), max(ys), mx.z))}


def apply_canonical(yaw_deg, mesh_objects, ports, clearance):
    """Rotate the building (mesh + ports + clearance) about Z by `yaw_deg` (0/None = no-op)."""
    if not yaw_deg:
        return clearance
    rot = Matrix.Rotation(math.radians(yaw_deg), 4, "Z")
    for obj in mesh_objects:
        obj.matrix_world = rot @ obj.matrix_world
    bpy.context.view_layer.update()
    rot3 = rot.to_3x3()
    for p in ports:
        p["pos"] = rot @ p["pos"]
        p["face"] = rot3 @ p["face"]
    return _rotate_box_z(clearance, rot) if clearance is not None else None


def snap_ports_to_surface(mesh_objects, ports, band=1.0, reach=3.0):
    """Move each port outward along its facing to the model's actual outer edge (the stored point is
    often recessed under an overhang). Scans mesh vertices within a narrow lateral band; then makes
    same-facing ports coplanar to their innermost snapped edge so a side reads as one clean row."""
    if not ports:
        return
    up = Vector((0.0, 0.0, 1.0))
    infos = []
    for port in ports:
        side = port["face"].cross(up)
        side = side.normalized() if side.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        infos.append({"side": side, "cur": port["pos"].dot(port["face"]), "best": None})

    for obj in mesh_objects:
        mw = obj.matrix_world
        for vtx in obj.data.vertices:
            w = mw @ vtx.co
            for port, info in zip(ports, infos, strict=True):
                if abs((w - port["pos"]).dot(info["side"])) > band:
                    continue
                proj = w.dot(port["face"])
                if proj < info["cur"] - band or proj > info["cur"] + reach:
                    continue
                if info["best"] is None or proj > info["best"]:
                    info["best"] = proj

    for port, info in zip(ports, infos, strict=True):
        info["snapped"] = info["best"] is not None and info["best"] > info["cur"]
        if info["snapped"]:
            port["pos"] = port["pos"] + port["face"] * (info["best"] - info["cur"])

    groups = {}
    for port, info in zip(ports, infos, strict=True):
        f = port["face"]
        groups.setdefault((round(f.x), round(f.y), round(f.z)), []).append((port, info))
    for grp in groups.values():
        f = grp[0][0]["face"]
        snapped = [p["pos"].dot(f) for p, i in grp if i["snapped"]]
        if not snapped:
            continue
        target = min(snapped)
        for p, _i in grp:
            p["pos"] = p["pos"] + f * (target - p["pos"].dot(f))


# --------------------------------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------------------------------
def _silhouette_material():
    """A flat opaque emission material. With ``film_transparent`` the rendered alpha is then a clean
    coverage silhouette (~1 where the mesh is, 0 elsewhere) for potrace to trace downstream. The
    color is irrelevant -- only the alpha and the (colorless) Freestyle strokes are consumed."""
    mat = bpy.data.materials.new("silhouette")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = (0.1, 0.28, 0.55, 1.0)
    nt.links.new(emi.outputs[0], out.inputs["Surface"])
    return mat


def setup_engine(mesh_objects, crease_deg, strokes_module):
    """EEVEE render of a colorless coverage silhouette (alpha == coverage via ``film_transparent``)
    with Freestyle in SCRIPT mode capturing feature-edge strokes to ``$SF_SVG_PATHS``.

    Both outputs are theme-independent: the raster is read only for its alpha (traced into the SVG
    fill) and the strokes are plain polylines, so Blender runs once and finalize colors per theme.
    Mirrors the proven ``render.py`` blueprint+SVG path (EEVEE, crease angle, SCRIPT module)."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    mat = _silhouette_material()
    for obj in mesh_objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    scene.render.use_freestyle = True
    view_layer = scene.view_layers[0]
    view_layer.use_freestyle = True
    fs = view_layer.freestyle_settings
    fs.mode = "SCRIPT"
    fs.crease_angle = math.radians(180.0 - crease_deg)
    for module in list(fs.modules):
        fs.modules.remove(module)
    text = bpy.data.texts.load(strokes_module)
    entry = fs.modules.new()
    entry.script = text
    entry.use = True


def make_camera():
    cam_data = bpy.data.cameras.new("ortho_cam")
    cam_data.type = "ORTHO"
    cam_obj = bpy.data.objects.new("ortho_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    return cam_obj


def project_ports(scene, cam_obj, ports, view_name, res_x, res_y, args):
    """Project each visible I/O port to a pixel rect for the marker overlay (near-face culled)."""
    if not ports:
        return []
    offset = Vector(VIEWS[view_name]["offset"]).normalized()
    up = Vector((0.0, 0.0, 1.0))
    inv = 1.0 / args.meters_per_unit
    size = args.port_size * inv
    half = 0.5 * size
    drop = args.port_drop * inv
    out = []
    for port in ports:
        face = port["face"]
        d = face.dot(offset)
        if d <= -0.15:  # facing away from the camera -> occluded
            continue
        reach = (args.port_pipe_size if port["kind"] == "pipe" else args.port_belt_size) * inv
        side = face.cross(up)
        side = side.normalized() if side.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        top = reach - drop
        xs, ys = [], []
        for su in (-1.0, 1.0):
            for sv in (top - size, top):
                w = port["pos"] + side * (half * su) + up * sv
                ndc = world_to_camera_view(scene, cam_obj, w)
                xs.append(ndc.x * res_x)
                ys.append((1.0 - ndc.y) * res_y)
        out.append(
            {
                "role": port["role"],
                "kind": port["kind"],
                "rect": [
                    round(min(xs), 1),
                    round(min(ys), 1),
                    round(max(xs), 1),
                    round(max(ys), 1),
                ],
                "face_on": abs(d) > 0.7,
            }
        )
    return out


def _power_occluded(scene, depsgraph, point, view_dir, eps=0.5, far=1000.0):
    """True if solid geometry sits between the camera side and the power nub (nub hidden behind the
    body for this view). ``view_dir`` is the unit offset from the model toward the camera; we cast a
    ray from far on the camera side back toward the model and compare the first hit's depth to the
    nub's: a hit clearly in front (> ``eps`` bu nearer the camera) means the nub is buried. A power
    nub sits proud of the surface, so from a side that sees it the first hit lands ~on it."""
    origin = point + view_dir * far
    hit = scene.ray_cast(depsgraph, origin, -view_dir)
    if not hit[0]:
        return False
    return (hit[1] - point).dot(view_dir) > eps


def project_power_ports(scene, cam_obj, power_ports, view_name, res_x, res_y, args):
    """Project each power connector as a positional point marker (a small square around its
    projected 3D point), occlusion-culled by ray-cast so it shows only on views that see the nub."""
    if not power_ports:
        return []
    view = VIEWS[view_name]
    view_dir = Vector(view["offset"]).normalized()
    haxis = Vector((0.0, 0.0, 0.0))
    vaxis = Vector((0.0, 0.0, 0.0))
    haxis[AXIS_INDEX[view["h"]]] = 1.0
    vaxis[AXIS_INDEX[view["v"]]] = 1.0
    half = 0.5 * args.port_size / args.meters_per_unit
    depsgraph = bpy.context.evaluated_depsgraph_get()
    out = []
    for port in power_ports:
        p = port["pos"]
        if _power_occluded(scene, depsgraph, p, view_dir):
            continue
        xs, ys = [], []
        for su in (-1.0, 1.0):
            for sv in (-1.0, 1.0):
                w = p + haxis * (half * su) + vaxis * (half * sv)
                ndc = world_to_camera_view(scene, cam_obj, w)
                xs.append(ndc.x * res_x)
                ys.append((1.0 - ndc.y) * res_y)
        out.append(
            {
                "role": "power",
                "kind": "power",
                "rect": [
                    round(min(xs), 1),
                    round(min(ys), 1),
                    round(max(xs), 1),
                    round(max(ys), 1),
                ],
                "face_on": True,
            }
        )
    return out


def render_view(cam_obj, mins, maxs, view_name, args, out_base, clearance_bu, ports, power_ports):
    """Render one view; return its manifest dict. Framing is grid-snapped from the mesh origin and
    expanded to also contain the clearance box; clearance corners + ports project to pixels."""
    view = VIEWS[view_name]
    mpu, ppm = args.meters_per_unit, args.ppm
    h_ax, v_ax = AXIS_INDEX[view["h"]], AXIS_INDEX[view["v"]]
    depth_ax = 3 - h_ax - v_ax

    min_h, max_h = mins[h_ax], maxs[h_ax]
    min_v, max_v = mins[v_ax], maxs[v_ax]
    content_w_m = (max_h - min_h) * mpu
    content_h_m = (max_v - min_v) * mpu

    if clearance_bu is not None:
        min_h = min(min_h, clearance_bu["min"][h_ax])
        max_h = max(max_h, clearance_bu["max"][h_ax])
        min_v = min(min_v, clearance_bu["min"][v_ax])
        max_v = max(max_v, clearance_bu["max"][v_ax])

    if args.grid and args.grid > 0:
        gbu = args.grid / mpu
        eps = 1e-6
        left = math.floor(min_h / gbu + eps) * gbu
        right = math.ceil(max_h / gbu - eps) * gbu
        bot = math.floor(min_v / gbu + eps) * gbu
        top = math.ceil(max_v / gbu - eps) * gbu
    else:
        left, right, bot, top = min_h, max_h, min_v, max_v

    width_m = (right - left) * mpu
    height_m = (top - bot) * mpu
    res_x = max(1, round(width_m * ppm))
    res_y = max(1, round(height_m * ppm))
    span_m = max(res_x, res_y) / ppm
    ortho_scale_bu = span_m / mpu

    scene = bpy.context.scene
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.resolution_percentage = 100
    cam_obj.data.ortho_scale = ortho_scale_bu
    cam_obj.rotation_euler = view["euler"]

    center = (mins + maxs) * 0.5
    target = Vector((0.0, 0.0, 0.0))
    target[h_ax] = (left + right) * 0.5
    target[v_ax] = (bot + top) * 0.5
    target[depth_ax] = center[depth_ax]
    max_dim = max(maxs[i] - mins[i] for i in range(3))
    dist = max_dim * 4.0 + 10.0
    cam_obj.location = target + Vector(view["offset"]) * dist
    cam_obj.data.clip_start = 0.001
    cam_obj.data.clip_end = dist * 4.0 + 10.0

    # Freestyle appends this view's strokes to a fresh .paths file (SCRIPT module reads the env).
    strokes_path = Path(args.strokes_dir) / f"{args.name}_{view_name}.paths"
    if strokes_path.exists():
        strokes_path.unlink()
    os.environ["SF_SVG_PATHS"] = str(strokes_path)

    out_path = Path(out_base) / f"{args.name}_{view_name}.png"
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)

    clearance_px = None
    if clearance_bu is not None:
        cmn, cmx = clearance_bu["min"], clearance_bu["max"]
        xs, ys = [], []
        for cx in (cmn[0], cmx[0]):
            for cy in (cmn[1], cmx[1]):
                for cz in (cmn[2], cmx[2]):
                    ndc = world_to_camera_view(scene, cam_obj, Vector((cx, cy, cz)))
                    xs.append(ndc.x * res_x)
                    ys.append((1.0 - ndc.y) * res_y)
        clearance_px = [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]

    ports_px = project_ports(scene, cam_obj, ports or [], view_name, res_x, res_y, args)
    ports_px += project_power_ports(
        scene, cam_obj, power_ports or [], view_name, res_x, res_y, args
    )
    gbu = (args.grid / mpu) if (args.grid and args.grid > 0) else 0
    print(f"[raster] {out_path.name}  {res_x}x{res_y} px  ({width_m:.2f} x {height_m:.2f} m)")
    return {
        "view": view_name,
        "origin_cells_from_left": round(-left / gbu) if gbu else None,
        "origin_cells_from_bottom": round(-bot / gbu) if gbu else None,
        "cells_w": round((right - left) / gbu) if gbu else None,
        "cells_h": round((top - bot) / gbu) if gbu else None,
        "clearance_px": clearance_px,
        "ports_px": ports_px,
        "file": out_path.name,
        "width_px": res_x,
        "height_px": res_y,
        "width_m": round(width_m, 4),
        "height_m": round(height_m, 4),
        "content_w_m": round(content_w_m, 4),
        "content_h_m": round(content_h_m, 4),
        "ppm": ppm,
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parse_args(argv)
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    Path(args.strokes_dir).mkdir(parents=True, exist_ok=True)
    Path(args.manifest_dir).mkdir(parents=True, exist_ok=True)
    name = args.name
    inv = 1.0 / args.meters_per_unit

    clear_scene()
    mesh_objects = import_model(args.input)
    if not mesh_objects:
        raise SystemExit(f"[render] no mesh objects imported from {args.input}")

    # Place the body where the blueprint puts it, then capture the body-only centre (the axis the
    # annot layer rotates about) BEFORE folding in the shared connector meshes.
    mesh_offset = _load_map(args.mesh_offsets, name)
    if mesh_offset:
        apply_mesh_offset(mesh_objects, mesh_offset, inv)
    bmn, bmx = world_bbox(mesh_objects)
    body_center = ((bmn[0] + bmx[0]) / 2.0, (bmn[1] + bmx[1]) / 2.0)

    conn_objs = []
    placements = load_connectors(args.connectors, name)
    if placements and args.connectors_dir:
        conn_objs = place_connectors(placements, args.connectors_dir, inv)
        mesh_objects = mesh_objects + conn_objs

    ports = load_ports(args.ports, name, args.meters_per_unit)
    clearance_m = load_clearance(args.clearance, name)

    annot = mesh_offset.get("annot") if mesh_offset else None
    if annot:
        apply_annot_offset(annot, ports, conn_objs, body_center, inv)

    # Canonical orientation for flow-through machines: send OUTPUT -> +Y (front). This runs even for
    # annot buildings -- annot only *co-locates* the port layer onto the body; canonicalizing then
    # rotates the whole assembly (body + ports + clearance, rigidly, keeping co-location) so the
    # accelerator ends up front=outputs like every other machine.
    if ports and not args.no_canonical:
        cyaw = canonical_yaw(ports)
        if cyaw:
            clearance_m = apply_canonical(cyaw, mesh_objects, ports, clearance_m)

    mins, maxs = robust_world_bbox(mesh_objects, args.bbox_gap / args.meters_per_unit)
    dims_bu = maxs - mins

    # Clearance box (m) -> blender units, snapped OUTWARD to whole grid cells so footprint ticks
    # land on grid lines (== image edges).
    clearance_bu = None
    if clearance_m is not None:
        clearance_bu = {"min": clearance_m["min"] * inv, "max": clearance_m["max"] * inv}
        if args.grid and args.grid > 0:
            gbu = args.grid / args.meters_per_unit
            eps = 1e-6
            mn, mx = clearance_bu["min"], clearance_bu["max"]
            clearance_bu = {
                "min": Vector(tuple(math.floor(mn[i] / gbu + eps) * gbu for i in range(3))),
                "max": Vector(tuple(math.ceil(mx[i] / gbu - eps) * gbu for i in range(3))),
            }

    # Power nubs ride the same body transforms above (annot / canonical) but are NOT belt/pipe
    # mouths: they get no edge-snap and no facing cull -- they're positional points.
    io_ports = [p for p in ports if p.get("kind") != "power"]
    power_ports = [p for p in ports if p.get("kind") == "power"]

    if io_ports and not args.no_port_snap:
        snap_ports_to_surface(mesh_objects, io_ports)

    strokes_module = str(Path(__file__).resolve().parent / "freestyle.py")
    setup_engine(mesh_objects, args.crease_deg, strokes_module)
    cam = make_camera()
    results = []
    for view in args.views.split(","):
        view = view.strip()
        if view not in VIEWS:
            print(f"[render] WARNING: unknown view '{view}' (skipped)", file=sys.stderr)
            continue
        results.append(
            render_view(
                cam, mins, maxs, view, args, args.outdir, clearance_bu, io_ports, power_ports
            )
        )

    manifest = {
        "name": name,
        "source": Path(args.input).name,
        "ppm": args.ppm,
        "grid_m": args.grid,
        "meters_per_unit": args.meters_per_unit,
        "bbox_m": {
            "x": round(dims_bu.x * args.meters_per_unit, 4),
            "y": round(dims_bu.y * args.meters_per_unit, 4),
            "z": round(dims_bu.z * args.meters_per_unit, 4),
        },
        "clearance_m": (
            {
                "min": [round(v * args.meters_per_unit, 3) for v in clearance_bu["min"]],
                "max": [round(v * args.meters_per_unit, 3) for v in clearance_bu["max"]],
            }
            if clearance_bu is not None
            else None
        ),
        "views": results,
    }
    manifest_path = Path(args.manifest_dir) / f"{name}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[manifest] {manifest_path.name}  ({len(results)} views)")


main()
