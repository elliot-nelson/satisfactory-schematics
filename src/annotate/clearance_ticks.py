"""FICSIT-orange clearance-footprint corner ticks, as SVG vectors.

The manifest's ``clearance_px`` is the projected pixel rect of the in-game clearance box (grid-
snapped to the image edges). We mark it with a short L-tick at each corner -- the true reserved
footprint -- rather than a full box, so it reads as a faint dimensional guide under the line art.
Ported from the old ``svg_export.svg_clearance``; the legacy PIL raster stamp
(``tools/draw_clearance_ticks.py``) is not carried since the SVG path is the official artifact.
"""

from __future__ import annotations

Rect = tuple[float, float, float, float]


def clearance_ticks_svg(rect: Rect, w: int, h: int, tick_rgba: tuple[int, int, int, int],
                        leg: int = 5) -> str:  # fmt: skip
    """Return the SVG ``<path>`` of four corner L-ticks for the clearance ``rect`` (x0,y0,x1,y1)."""
    x0, y0, x1, y1 = rect
    x1 = min(x1, w - 1)
    y1 = min(y1, h - 1)
    if x1 < x0 or y1 < y0:
        return ""
    segs = []
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        segs.append(f"M{cx:.1f},{cy:.1f} L{cx + dx * leg:.1f},{cy:.1f}")
        segs.append(f"M{cx:.1f},{cy:.1f} L{cx:.1f},{cy + dy * leg:.1f}")
    r, g, b, a = tick_rgba
    return (
        f'<path d="{" ".join(segs)}" stroke="rgb({r},{g},{b})" '
        f'stroke-opacity="{a / 255.0:.3f}" stroke-width="1" fill="none"/>'
    )
