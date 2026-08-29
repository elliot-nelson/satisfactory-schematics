"""Finalize stage driver (host, pure Python -- no Blender).

For the selected theme, turn each rendered view (raster alpha + Freestyle strokes + manifest) into a
themed SVG under ``build/04-svg/<theme>/`` plus a rasterized PNG under ``build/05-png/<theme>/``.
Each PNG is just the SVG rasterized at its native size (so the two can't drift), skipped only if
``rsvg-convert`` is missing. Theme-dependent and incremental (skips a view whose SVG is newer than
all its inputs unless ``force``). This is the per-theme pass; everything it reads is shared.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import PNG_DIR, RENDER_DIR, SVG_DIR, ensure
from src.common.plan import BuildPlan, StageError
from src.common.theme import ThemeError, load_theme
from src.finalize import rasterize as R
from src.finalize.svg import assemble

RASTER_DIR = RENDER_DIR / "raster"
STROKES_DIR = RENDER_DIR / "strokes"
MANIFEST_DIR = RENDER_DIR / "manifests"


def _read_alpha(png_path: Path) -> np.ndarray | None:
    """Load the raster's alpha channel as a 2D array, rows BOTTOM-up (as trace_fill expects)."""
    if not png_path.is_file():
        return None
    with Image.open(png_path) as img:
        arr = np.asarray(img.convert("RGBA"), dtype=np.float32)
    return np.flipud(arr[:, :, 3] / 255.0)


def _manifests(plan: BuildPlan) -> list[Path]:
    if not MANIFEST_DIR.is_dir():
        raise StageError(
            f"no render manifests at {MANIFEST_DIR}. Run `./schematic build` (render) first."
        )
    found = sorted(MANIFEST_DIR.glob("*.json"))
    if plan.only:
        found = [p for p in found if p.stem in plan.only]
        missing = plan.only - {p.stem for p in found}
        if missing:
            raise StageError(f"--only not rendered yet: {', '.join(sorted(missing))}")
    if not found:
        raise StageError(f"no manifests to finalize in {MANIFEST_DIR}.")
    return found


def _up_to_date(svg: Path, inputs: list[Path]) -> bool:
    if not svg.exists():
        return False
    svg_mtime = svg.stat().st_mtime
    return all(inp.exists() and inp.stat().st_mtime <= svg_mtime for inp in inputs)


def run(cfg: Config, plan: BuildPlan) -> None:
    """Assemble per-theme SVGs + PNGs from the rasters, strokes, and manifests."""
    try:
        theme = load_theme(plan.theme)
    except ThemeError as exc:
        raise StageError(str(exc)) from exc

    style = theme.style(potrace=cfg.tools.potrace.bin or "potrace")
    rsvg_bin = cfg.tools.rsvg.bin or "rsvg-convert"
    png_ok = R.rsvg_available(rsvg_bin)
    if not png_ok:
        C.console.print(f"[yellow]![/] {rsvg_bin} not found -> skipping PNG (brew install librsvg)")

    svg_out = ensure(SVG_DIR / theme.slug)
    png_out = ensure(PNG_DIR / theme.slug) if png_ok else None
    views_filter = set(plan.views) if plan.views else None

    n_svg = n_png = 0
    for manifest_path in _manifests(plan):
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = man["name"]
        C.rule(f"{name}  ({theme.name})")
        for view in man.get("views", []):
            vname = view["view"]
            if views_filter and vname not in views_filter:
                continue
            raster = RASTER_DIR / f"{name}_{vname}.png"
            strokes = STROKES_DIR / f"{name}_{vname}.paths"
            svg_path = svg_out / f"{name}_{vname}.svg"
            if not plan.force and _up_to_date(svg_path, [raster, strokes, manifest_path]):
                C.console.print(f"[dim]skip[/] {svg_path.name} (up to date)")
            else:
                alpha = _read_alpha(raster)
                svg_str, n_lines = assemble(strokes, alpha, view, style)
                svg_path.write_text(svg_str, encoding="utf-8")
                n_svg += 1
                C.console.print(
                    f"  {svg_path.name}  {view['width_px']}x{view['height_px']} px "
                    f"[dim]({n_lines} line paths)[/]"
                )
            if png_out is not None:
                png_path = png_out / f"{name}_{vname}.png"
                stale = plan.force or not _up_to_date(png_path, [svg_path])
                if stale and R.rasterize(svg_path, png_path, rsvg_bin):
                    n_png += 1

    summary = f"[green]Finalize complete[/] -> {svg_out}  ({n_svg} SVG"
    if png_out is not None:
        summary += f", {n_png} PNG"
    C.console.print(f"\n{summary})")
