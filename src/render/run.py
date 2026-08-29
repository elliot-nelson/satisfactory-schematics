"""Host-side driver for the Blender render stage.

Locates Blender, then for each extracted building body (``build/01-extract/models/*.glb``) spawns
``blender -b -P blender/entry.py``, passing the prepare-stage contracts so the body is oriented
into the blueprint frame. Blender writes per-view alpha silhouettes into ``build/03-render/raster/``
and a projection manifest into ``build/03-render/manifests/``. Theme-independent and incremental
(skips a model when its rasters + manifest already exist, unless ``force``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import EXTRACT_DIR, PREPARE_DIR, RENDER_DIR, ensure
from src.common.plan import BuildPlan, StageError

ENTRY = Path(__file__).resolve().parent / "blender" / "entry.py"
MODELS_DIR = EXTRACT_DIR / "models"
CONNECTORS_DIR = EXTRACT_DIR / "models" / "connectors"
RASTER_DIR = RENDER_DIR / "raster"
STROKES_DIR = RENDER_DIR / "strokes"
MANIFEST_DIR = RENDER_DIR / "manifests"


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
    raise StageError(
        f"Blender not found (checked ${env_var}, PATH, /Applications). "
        f"Run `./schematic doctor` to install it, or set ${env_var}=/path/to/blender."
    )


def _models(plan: BuildPlan) -> list[Path]:
    if not MODELS_DIR.is_dir():
        raise StageError(f"no extracted models at {MODELS_DIR}. Run `./schematic extract` first.")
    globbed = sorted(MODELS_DIR.glob("*.glb"))
    if plan.only:
        globbed = [p for p in globbed if p.stem in plan.only]
        missing = plan.only - {p.stem for p in globbed}
        if missing:
            raise StageError(f"--only not found in {MODELS_DIR}: {', '.join(sorted(missing))}")
    if not globbed:
        raise StageError(f"no .glb bodies to render in {MODELS_DIR}.")
    return globbed


def _needs_render(name: str, views: list[str]) -> bool:
    if not (MANIFEST_DIR / f"{name}.json").exists():
        return True
    return any(
        not (RASTER_DIR / f"{name}_{v}.png").exists()
        or not (STROKES_DIR / f"{name}_{v}.paths").exists()
        for v in views
    )


def _prepare_arg(flag: str, path: Path) -> list[str]:
    """Pass a prepare contract only if it exists (render degrades gracefully without it)."""
    return [flag, str(path)] if path.exists() else []


def run(cfg: Config, plan: BuildPlan) -> None:
    """Render silhouettes + projection manifests for the selected building bodies."""
    blender = find_blender(cfg)
    views = plan.views or cfg.render.views
    models = _models(plan)
    ensure(RASTER_DIR)
    ensure(STROKES_DIR)
    ensure(MANIFEST_DIR)

    rendered = 0
    for glb in models:
        name = glb.stem
        if not plan.force and not _needs_render(name, views):
            C.console.print(f"[dim]skip[/] {name} (up to date; --force to redo)")
            continue
        C.rule(f"{name}  ({len(views)} views)")
        cmd = [
            blender, "-b", "-P", str(ENTRY), "--",
            "--input", str(glb),
            "--outdir", str(RASTER_DIR),
            "--strokes-dir", str(STROKES_DIR),
            "--manifest-dir", str(MANIFEST_DIR),
            "--name", name,
            "--views", ",".join(views),
            "--ppm", str(cfg.render.ppm),
            "--grid", str(cfg.render.grid),
            "--meters-per-unit", str(cfg.render.metersPerUnit),
            "--connectors-dir", str(CONNECTORS_DIR),
            *_prepare_arg("--clearance", PREPARE_DIR / "clearance.json"),
            *_prepare_arg("--ports", PREPARE_DIR / "ports.json"),
            *_prepare_arg("--mesh-offsets", PREPARE_DIR / "mesh_offsets.json"),
            *_prepare_arg("--connectors", PREPARE_DIR / "connectors.json"),
        ]  # fmt: skip
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            C.err_console.print(proc.stdout)
            C.err_console.print(proc.stderr)
            raise StageError(f"Blender failed on {name} (exit {proc.returncode}).")
        for line in proc.stdout.splitlines():
            if line.startswith("[raster]"):
                C.console.print(f"  {line[9:]}")
            elif line.startswith("[manifest]"):
                C.console.print(f"  [dim]{line[11:]}[/]")
        rendered += 1

    C.console.print(f"\n[green]Render complete[/] -> {RENDER_DIR}  ({rendered} rendered)")
