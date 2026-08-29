"""Host-side driver for the Blender raster stage.

Locates Blender, then for each extracted building body (``build/01-extract/models/*.glb``) spawns
``blender -b -P blender/entry.py`` to write per-view alpha silhouettes into
``build/03-render/raster/``. Theme-independent and incremental (skips models whose rasters already
exist unless ``force``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import EXTRACT_DIR, RENDER_DIR, ensure

ENTRY = Path(__file__).resolve().parent / "blender" / "entry.py"
MODELS_DIR = EXTRACT_DIR / "models"
RASTER_DIR = RENDER_DIR / "raster"


class RenderError(Exception):
    """User-actionable render failure (Blender missing, no models, a failed render)."""


@dataclass
class RenderPlan:
    only: set[str] = field(default_factory=set)
    views: list[str] | None = None  # None -> config default
    force: bool = False


def find_blender(cfg: Config) -> str:
    """Resolve the Blender binary: $BLENDER (name from config) -> PATH -> the macOS app bundle."""
    env_var = cfg.tools.blender.env
    candidates = [
        os.environ.get(env_var),
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise RenderError(
        f"Blender not found (checked ${env_var}, PATH, /Applications). "
        f"Run `./sat doctor` to install it, or set ${env_var}=/path/to/blender."
    )


def _models(plan: RenderPlan) -> list[Path]:
    if not MODELS_DIR.is_dir():
        raise RenderError(f"no extracted models at {MODELS_DIR}. Run `./sat extract` first.")
    globbed = sorted(MODELS_DIR.glob("*.glb"))
    if plan.only:
        globbed = [p for p in globbed if p.stem in plan.only]
        missing = plan.only - {p.stem for p in globbed}
        if missing:
            raise RenderError(f"--only not found in {MODELS_DIR}: {', '.join(sorted(missing))}")
    if not globbed:
        raise RenderError(f"no .glb bodies to render in {MODELS_DIR}.")
    return globbed


def _needs_render(name: str, views: list[str]) -> bool:
    return any(not (RASTER_DIR / f"{name}_{v}.png").exists() for v in views)


def run_render(cfg: Config, plan: RenderPlan) -> None:
    """Render alpha-silhouette rasters for the selected building bodies."""
    blender = find_blender(cfg)
    views = plan.views or cfg.render.views
    models = _models(plan)
    ensure(RASTER_DIR)

    rendered = 0
    for glb in models:
        name = glb.stem
        if not plan.force and not _needs_render(name, views):
            C.console.print(f"[dim]skip[/] {name} (rasters present; --force to redo)")
            continue
        C.rule(f"{name}  ({len(views)} views)")
        cmd = [
            blender, "-b", "-P", str(ENTRY), "--",
            "--input", str(glb),
            "--outdir", str(RASTER_DIR),
            "--name", name,
            "--views", ",".join(views),
            "--ppm", str(cfg.render.ppm),
            "--grid", str(cfg.render.grid),
            "--meters-per-unit", str(cfg.render.metersPerUnit),
        ]  # fmt: skip
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            C.err_console.print(proc.stdout)
            C.err_console.print(proc.stderr)
            raise RenderError(f"Blender failed on {name} (exit {proc.returncode}).")
        for line in proc.stdout.splitlines():
            if line.startswith("[raster]"):
                C.console.print(f"  {line[9:]}")
        rendered += 1

    C.console.print(f"\n[green]Render complete[/] -> {RASTER_DIR}  ({rendered} rendered)")
