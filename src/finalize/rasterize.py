"""Rasterize a finished SVG to PNG with ``rsvg-convert``.

A PNG is never a second Blender render -- it is just the official SVG rasterized at its native pixel
size, so the vector and raster can't drift. Optional: if ``rsvg-convert`` is missing we skip PNGs
with a message (same graceful degradation as the old ``run.sh --png``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def rsvg_available(binary: str = "rsvg-convert") -> bool:
    return shutil.which(binary) is not None


def rasterize(svg_path: Path, png_path: Path, binary: str = "rsvg-convert") -> bool:
    """Rasterize ``svg_path`` -> ``png_path`` at the SVG's native size. Returns True on success."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [binary, str(svg_path), "-o", str(png_path)],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return False
    return png_path.exists()
