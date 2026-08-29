"""Trace the render's alpha silhouette into one flat semi-transparent SVG fill (potrace).

The Blender raster is colorless; we read only its **alpha coverage** and vectorize it into a single
evenodd fill path that sits under the line art. The mask is eroded a hair so the fill stays inside
the feature outline instead of saran-wrapping past it. Ported from the old
``svg_export.trace_fill``; returns ``""`` (skipped) if potrace is missing or nothing traces.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np


def trace_fill(alpha: np.ndarray, w: int, h: int, erode: int, fill_hex: str, fill_alpha: float,
               thresh: float = 0.12, potrace: str = "potrace") -> str:  # fmt: skip
    """Vectorize the coverage mask of ``alpha`` (2D, rows BOTTOM-up, 0..1) into an SVG ``<g>`` fill.

    Erodes the mask by ``erode`` px, writes a PGM, runs potrace, and reuses potrace's own y-flip
    transform so the path lands in our top-left viewBox. Empty string on any failure."""
    mask_bool = alpha > thresh
    for _ in range(max(0, int(erode))):
        eroded = mask_bool.copy()
        eroded[1:, :] &= mask_bool[:-1, :]
        eroded[:-1, :] &= mask_bool[1:, :]
        eroded[:, 1:] &= mask_bool[:, :-1]
        eroded[:, :-1] &= mask_bool[:, 1:]
        mask_bool = eroded
    mask = np.where(mask_bool, 0, 255).astype(np.uint8)
    mask = np.flipud(mask)  # bottom-up -> top-down for potrace

    with tempfile.TemporaryDirectory() as tmp:
        pgm = Path(tmp) / "silhouette.pgm"
        svg = Path(tmp) / "silhouette.svg"
        with pgm.open("wb") as fh:
            fh.write(b"P5\n%d %d\n255\n" % (w, h))
            fh.write(mask.tobytes())
        try:
            subprocess.run(
                [potrace, str(pgm), "-s", "-t", "8", "-o", str(svg)],
                check=True,
                capture_output=True,
            )
            data = svg.read_text()
        except (subprocess.CalledProcessError, OSError):
            return ""

    tm = re.search(r'transform="([^"]*)"', data)
    ds = re.findall(r'<path d="([^"]*)"', data)
    if not tm or not ds:
        return ""
    return (
        f'<g transform="{tm.group(1)}"><path d="{" ".join(ds)}" fill="{fill_hex}" '
        f'fill-opacity="{fill_alpha:.3f}" fill-rule="evenodd" stroke="none"/></g>'
    )
