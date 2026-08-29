"""Runs INSIDE Blender: ``blender -b -P entry.py -- <args>``.

Produces per-view, true-to-scale orthographic **alpha silhouette** rasters for one ``.glb``.
Theme-independent (colorless geometry only). Self-contained on purpose -- it imports just
``bpy`` / ``mathutils`` / stdlib, because Blender runs it in its own interpreter without our
package on the path.

Framing is ported from the proven standalone renderer (SPEC.md 12.4 / 12.10):
  * true-to-scale: 1 m -> ``ppm`` px, locked via ortho_scale = max(res)/ppm,
  * grid-snapped: each frame edge pushed to the next whole grid cell measured from the mesh
    origin (0,0,0) = the in-game snap point, so tiled images line up exactly as in game.

Deferred to later passes (need `prepare` data): mesh offsets, canonical yaw, connectors,
clearance/port projection, Freestyle strokes. This is just the raster.
"""

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HALF_PI = math.pi / 2
PI = math.pi

# Which world axes map to the image's horizontal/vertical, plus the camera orientation and the
# unit offset direction it sits along. front/back and left/right are swapped vs the raw Blender
# axes so the labels match Satisfactory's I/O convention (SPEC.md 12.8).
VIEWS = {
    "top":   {"euler": (0.0,     0.0,  0.0),     "offset": (0, 0, 1),  "h": "x", "v": "y"},
    "front": {"euler": (HALF_PI, 0.0,  PI),      "offset": (0, 1, 0),  "h": "x", "v": "z"},
    "back":  {"euler": (HALF_PI, 0.0,  0.0),     "offset": (0, -1, 0), "h": "x", "v": "z"},
    "right": {"euler": (HALF_PI, 0.0, -HALF_PI), "offset": (-1, 0, 0), "h": "y", "v": "z"},
    "left":  {"euler": (HALF_PI, 0.0,  HALF_PI), "offset": (1, 0, 0),  "h": "y", "v": "z"},
}  # fmt: skip

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def parse_args(argv):
    p = argparse.ArgumentParser(description="Orthographic alpha-silhouette raster (one model).")
    p.add_argument("--input", required=True, help="Path to a .glb / .gltf.")
    p.add_argument("--outdir", required=True, help="Directory for <name>_<view>.png.")
    p.add_argument("--name", required=True, help="Output stem (building key).")
    p.add_argument("--views", default="top,front,back,left,right", help="Comma-separated views.")
    p.add_argument("--ppm", type=float, default=20.0, help="Pixels per meter.")
    p.add_argument("--grid", type=float, default=1.0, help="Grid-snap cell size in meters (0=off).")
    p.add_argument("--meters-per-unit", type=float, default=1.0, help="glTF is already meters.")
    p.add_argument(
        "--robust-gap",
        type=float,
        default=0.0,
        help="Trim geometry separated by a gap larger than this (meters). 0=off.",
    )
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            block.remove(item)


def import_model(path):
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def world_bbox(mesh_objects):
    """(min_corner, max_corner) in world space over all mesh objects' bound boxes."""
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


def setup_engine():
    """Fast, colorless silhouette: Workbench over a transparent film -> alpha == coverage."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def make_camera():
    cam_data = bpy.data.cameras.new("ortho_cam")
    cam_data.type = "ORTHO"
    cam_obj = bpy.data.objects.new("ortho_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    return cam_obj


def render_view(cam_obj, mins, maxs, view_name, args, out_base):
    """Render one view to <out_base>_<view>.png. mins/maxs are world-space bbox corners (BU)."""
    view = VIEWS[view_name]
    mpu = args.meters_per_unit
    ppm = args.ppm

    h_ax = AXIS_INDEX[view["h"]]
    v_ax = AXIS_INDEX[view["v"]]
    depth_ax = 3 - h_ax - v_ax

    min_h, max_h = mins[h_ax], maxs[h_ax]
    min_v, max_v = mins[v_ax], maxs[v_ax]

    # Grid snap: push each edge to the next whole cell, measured from the origin (0,0,0), so the
    # image's grid coincides with the world grid and the machine's true offset is preserved.
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

    # Lock pixel size to exactly 1/ppm m by deriving ortho_scale from the larger pixel dimension.
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

    out_path = Path(args.outdir) / f"{args.name}_{view_name}.png"
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)
    print(f"[raster] {out_path.name}  {res_x}x{res_y} px  ({width_m:.2f} x {height_m:.2f} m)")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parse_args(argv)
    Path(args.outdir).mkdir(parents=True, exist_ok=True)

    clear_scene()
    mesh_objects = import_model(args.input)
    if not mesh_objects:
        raise SystemExit(f"[render] no mesh objects imported from {args.input}")

    gap_bu = (args.robust_gap / args.meters_per_unit) if args.robust_gap > 0 else 0.0
    mins, maxs = robust_world_bbox(mesh_objects, gap_bu)

    setup_engine()
    cam = make_camera()
    for view in args.views.split(","):
        view = view.strip()
        if view not in VIEWS:
            raise SystemExit(f"[render] unknown view: {view}")
        render_view(cam, mins, maxs, view, args, args.outdir)


main()
