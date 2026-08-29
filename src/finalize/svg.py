"""Assemble one view's SVG from the theme-independent render outputs.

Three colorless sources compose into a themed vector drawing:
  * **fill**  -- the raster's alpha silhouette, potrace-traced into a flat semi-transparent path
    (:mod:`src.finalize.trace_fill`);
  * **lines** -- the Freestyle ``.paths`` strokes, stitched into long chains, Ramer-Douglas-Peucker
    simplified, and given a touch of hand-drawn jitter;
  * **overlays** -- clearance corner ticks + I/O port markers as SVG vectors (:mod:`src.annotate`).

The SVG's width/height/viewBox are the manifest's grid-snapped pixel size, so each file is an exact
N x M grid of cells that drops onto a diagramming tool true-to-scale. Ported from the old
``svg_export`` (the stitch/RDP/read-stroke helpers are 1:1); overlays now live in ``src/annotate``.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from src.annotate.clearance_ticks import clearance_ticks_svg
from src.annotate.ports import ports_svg
from src.finalize.trace_fill import trace_fill

Point = tuple[float, float]
Polyline = list[Point]


def stitch(polylines: list[Polyline], q: float = 0.75) -> list[Polyline]:
    """Merge polylines sharing an endpoint (within ``q`` px) into longer chains."""

    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] / q), round(p[1] / q))

    ends: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, pl in enumerate(polylines):
        ends[key(pl[0])].append(i)
        ends[key(pl[-1])].append(i)
    used = [False] * len(polylines)
    out: list[Polyline] = []
    for i in range(len(polylines)):
        if used[i]:
            continue
        used[i] = True
        chain = list(polylines[i])
        for forward in (True, False):
            growing = True
            while growing:
                growing = False
                tail = chain[-1] if forward else chain[0]
                for j in ends.get(key(tail), ()):
                    if used[j]:
                        continue
                    seg = polylines[j]
                    if key(seg[0]) != key(tail):
                        seg = seg[::-1]
                    if key(seg[0]) != key(tail):
                        continue
                    if forward:
                        chain.extend(seg[1:])
                    else:
                        chain[:0] = seg[1:][::-1]
                    used[j] = True
                    growing = True
                    break
        out.append(chain)
    return out


def rdp(pts: Polyline, eps: float) -> Polyline:
    """Ramer-Douglas-Peucker point reduction."""
    n = len(pts)
    if n < 3 or eps <= 0:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        maxd, idx = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            if length_sq == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if d > maxd:
                maxd, idx = d, k
        if maxd > eps and idx != -1:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [pts[k] for k in range(n) if keep[k]]


def read_strokes(path: Path, h_img: int) -> list[Polyline]:
    """Read a ``.paths`` file (``x,y x,y ...`` per line, BOTTOM-left origin) into point lists
    flipped into the SVG's top-left origin. Drops non-finite vertices Freestyle sometimes emits."""
    loops: list[Polyline] = []
    if not path or not path.is_file():
        return loops
    for line in path.read_text().splitlines():
        pts = line.split()
        if len(pts) < 2:
            continue
        loop: Polyline = []
        for pt in pts:
            xs, ys = pt.split(",")
            x, y = float(xs), float(ys)
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            loop.append((x, h_img - y))
        if len(loop) >= 2:
            loops.append(loop)
    return loops


def assemble(strokes_path: Path, alpha: np.ndarray | None, man: dict[str, Any],
             style: dict[str, Any]) -> tuple[str, int]:  # fmt: skip
    """Build the full SVG string for one view. ``alpha`` is the raster's numpy alpha (bottom-up) or
    None; ``man`` is the manifest's per-view dict; ``style`` is the theme's flattened look knobs."""
    w, h = man["width_px"], man["height_px"]
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    ]

    # Silhouette fill (under the lines).
    if alpha is not None and style["fill_alpha"] > 0:
        grp = trace_fill(
            alpha, w, h, style["fill_erode"], style["fill_hex"], style["fill_alpha"],
            potrace=style.get("potrace", "potrace"),
        )  # fmt: skip
        if grp:
            body.append(grp)

    # Feature-edge lines: stitch + simplify + optional jitter.
    loops = read_strokes(strokes_path, h)
    if style["stitch"]:
        loops = stitch(loops)
    loops = [rdp(loop, style["rdp"]) for loop in loops]
    loops = [loop for loop in loops if len(loop) >= 2]
    jitter = style["jitter"]
    rng = random.Random(1234)
    polylines = []
    for loop in loops:
        if jitter > 0:
            pts = " ".join(
                f"{x + rng.uniform(-jitter, jitter):.2f},{y + rng.uniform(-jitter, jitter):.2f}"
                for x, y in loop
            )
        else:
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in loop)
        polylines.append(f'<polyline points="{pts}"/>')
    body.append(
        f'<g fill="none" stroke="{style["line_hex"]}" stroke-width="{style["line_width"]:.2f}" '
        f'stroke-linecap="round" stroke-linejoin="round">{"".join(polylines)}</g>'
    )

    if style.get("show_ticks", True) and man.get("clearance_px"):
        body.append(clearance_ticks_svg(man["clearance_px"], w, h, style["tick_rgba"]))
    if style.get("highlight_ports", True) and man.get("ports_px"):
        body.append(ports_svg(man["ports_px"], w, h, style["in_rgb"], style["out_rgb"]))
    body.append("</svg>")
    return "\n".join(body), len(loops)
