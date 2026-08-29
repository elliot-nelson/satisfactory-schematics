"""I/O port markers as SVG vectors: red input / green output squares, bars, and pipe circles.

The manifest's ``ports_px`` lists each visible belt/pipe port as a pixel rect with ``role`` (input/
output), ``kind`` (belt/pipe), and ``face_on`` (whether the camera sees the mouth head-on or
edge-on). We draw a crisp rounded-square + flow glyph for face-on belts, a thin bar for edge-on
belts, and a radial-gradient circle/ellipse for pipes (so they read as round tubes). Ported from the
old ``svg_export.svg_ports``; the legacy PIL raster stamp (``tools/draw_ports.py``) is not carried
since the SVG path is the official artifact.
"""

from __future__ import annotations

import colorsys
from typing import Any

Rgb = tuple[int, int, int]


def _norm(rect: list[float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = rect
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return x0, y0, x1, y1


def _glyph(role: str, x0: float, y0: float, x1: float, y1: float, stroke: str) -> str:
    """A flow glyph inside a face-on marker: hamburger bars for inputs, a chevron for outputs."""
    w, h = x1 - x0, y1 - y0
    if w < 10 or h < 10:
        return ""
    common = f'stroke="{stroke}" stroke-width="1.4" fill="none" stroke-linecap="round"'
    if role == "input":  # hamburger
        px = w * 0.28
        return "".join(
            f'<line x1="{x0 + px:.1f}" y1="{y0 + h * fr:.1f}" '
            f'x2="{x1 - px:.1f}" y2="{y0 + h * fr:.1f}" {common}/>'
            for fr in (0.32, 0.5, 0.68)
        )
    lx, rx = x0 + w * 0.36, x0 + w * 0.64  # chevron '>'
    return (
        f'<polyline points="{lx:.1f},{y0 + h * 0.30:.1f} {rx:.1f},{y0 + h * 0.5:.1f} '
        f'{lx:.1f},{y0 + h * 0.70:.1f}" {common}/>'
    )


def _toward_white(rgb: Rgb, desat: float = 0.4, lighten: float = 0.6) -> Rgb:
    """Push a color toward white (drop saturation, lift lightness) for the pipe gradient center."""
    r, g, b = (c / 255.0 for c in rgb)
    hue, lgt, sat = colorsys.rgb_to_hls(r, g, b)
    sat *= 1.0 - desat
    lgt = lgt + (1.0 - lgt) * lighten
    r, g, b = colorsys.hls_to_rgb(hue, lgt, sat)
    return (round(r * 255), round(g * 255), round(b * 255))


def ports_svg(ports_px: list[dict[str, Any]], w_img: int, h_img: int, in_rgb: Rgb,
              out_rgb: Rgb) -> str:  # fmt: skip
    """Return the SVG markup (``<defs>`` + shapes) for every visible port in ``ports_px``."""
    out: list[str] = []
    pipe_roles: set[str] = set()  # roles needing a radial-gradient def (bright center -> rim)
    for p in ports_px:
        role = p["role"]
        rgb = in_rgb if role == "input" else out_rgb
        stroke = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
        x0, y0, x1, y1 = _norm(p["rect"])
        x0 = max(0, min(x0, w_img - 1))
        x1 = max(0, min(x1, w_img - 1))
        y0 = max(0, min(y0, h_img - 1))
        y1 = max(0, min(y1, h_img - 1))
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        edge = f'stroke="{stroke}" stroke-opacity="0.92" stroke-width="2"'

        # Pipes reuse the belt marker SHAPE but with a radial gradient (bright, desaturated
        # center -> saturated rim) so they read as round tubes. Face-on: a full circle. Edge-on
        # (from the top): keep the bar footprint but bulge it thicker + brighten the center.
        if p.get("kind") == "pipe":
            pipe_roles.add(role)
            grad = f'fill="url(#pipegrad_{role})"'
            if p.get("face_on"):
                rad = max(3.0, min(w, h) / 2)
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" {edge} {grad}/>')
            else:
                bulge = 3.5  # center half-thickness; belt bar is 2.0, so a pipe swells a bit
                if w < h:  # bar runs vertically
                    rx, ry = bulge, max(4.0, h / 2)
                else:  # bar runs horizontally
                    rx, ry = max(4.0, w / 2), bulge
                thin = f'stroke="{stroke}" stroke-opacity="0.92" stroke-width="1"'
                out.append(
                    f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                    f"{thin} {grad}/>"
                )
        elif p.get("face_on"):
            fill = f'fill="{stroke}" fill-opacity="0.216"'
            r = max(2.0, min(w, h) * 0.22)
            out.append(
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="{r:.1f}" ry="{r:.1f}" {edge} {fill}/>'
            )
            out.append(_glyph(role, x0, y0, x1, y1, stroke))
        else:
            thick = 4.0
            if w < h:
                x0, x1 = cx - thick / 2, cx + thick / 2
            else:
                y0, y1 = cy - thick / 2, cy + thick / 2
            out.append(
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" '
                f'rx="1.5" fill="{stroke}" fill-opacity="0.588" stroke="{stroke}" '
                f'stroke-opacity="0.92" stroke-width="1"/>'
            )

    defs = []
    for role in sorted(pipe_roles):
        rgb = in_rgb if role == "input" else out_rgb
        cen = _toward_white(rgb)
        cc = f"rgb({cen[0]},{cen[1]},{cen[2]})"
        rc = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
        defs.append(
            f'<radialGradient id="pipegrad_{role}" cx="50%" cy="50%" r="50%">'
            f'<stop offset="0%" stop-color="{cc}" stop-opacity="0.92"/>'
            f'<stop offset="55%" stop-color="{cc}" stop-opacity="0.55"/>'
            f'<stop offset="100%" stop-color="{rc}" stop-opacity="0.75"/>'
            f"</radialGradient>"
        )
    prefix = ("<defs>" + "".join(defs) + "</defs>") if defs else ""
    return prefix + "".join(out)
