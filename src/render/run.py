"""Host-side driver for the Blender render stage.

Locates Blender, then for each extracted building body (``build/01-extract/models/*.glb``) spawns
``blender -b -P blender/entry.py``, passing the prepare-stage JSON so the body gets oriented into
the blueprint frame. Segment pieces (belts/pipes/beams/junctions, from ``models/segments/``) get a
second pass -- Blender tiles/bends the source tile into each named piece (belt_4m, belt_corner...).
Blender writes per-view alpha silhouettes into ``build/03-render/raster/`` and a projection manifest
into ``build/03-render/manifests/``. Theme-independent and incremental (skips a piece when its
rasters + manifest already exist, unless ``force``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import EXTRACT_DIR, PREPARE_DIR, RENDER_DIR, ensure
from src.common.buildings import load_catalog
from src.common.plan import BuildPlan, StageError
from src.common.segments import SegmentJob, segment_jobs

ENTRY = Path(__file__).resolve().parent / "blender" / "entry.py"
MODELS_DIR = EXTRACT_DIR / "models"
SEGMENTS_DIR = EXTRACT_DIR / "models" / "segments"
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
    return globbed


def _segments(cfg: Config, plan: BuildPlan) -> list[SegmentJob]:
    """Segment jobs whose source .glb was actually extracted (belts/pipes/beams/junctions)."""
    if not SEGMENTS_DIR.is_dir():
        return []
    jobs = [
        j
        for j in segment_jobs(load_catalog(cfg), cfg.render.segmentLengths)
        if (SEGMENTS_DIR / f"{j.source}.glb").exists()
    ]
    if plan.only:
        jobs = [j for j in jobs if j.name in plan.only]
    return jobs


def _needs_render(name: str, views: list[str]) -> bool:
    if not (MANIFEST_DIR / f"{name}.json").exists():
        return True
    return any(
        not (RASTER_DIR / f"{name}_{v}.png").exists()
        or not (STROKES_DIR / f"{name}_{v}.paths").exists()
        for v in views
    )


def _prepare_arg(flag: str, path: Path) -> list[str]:
    """Only pass a prepare file if it's actually there (render still works without it)."""
    return [flag, str(path)] if path.exists() else []


def _invoke(blender: str, name: str, extra: list[str]) -> None:
    """Spawn Blender for one job and surface its raster/manifest log lines."""
    cmd = [
        blender, "-b", "-P", str(ENTRY), "--",
        "--outdir", str(RASTER_DIR),
        "--strokes-dir", str(STROKES_DIR),
        "--manifest-dir", str(MANIFEST_DIR),
        "--name", name,
        *extra,
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


def _common_args(cfg: Config, glb: Path, views: list[str]) -> list[str]:
    return [
        "--input", str(glb),
        "--views", ",".join(views),
        "--ppm", str(cfg.render.ppm),
        "--grid", str(cfg.render.grid),
        "--meters-per-unit", str(cfg.render.metersPerUnit),
    ]  # fmt: skip


def _segment_args(job: SegmentJob) -> list[str]:
    extra = ["--kind", job.kind]
    if job.tile_length:
        extra += ["--tile-length", str(job.tile_length), "--tile-axis", job.tile_axis]
    if job.corner_radius:
        extra += ["--corner-radius", str(job.corner_radius)]
    return extra


def run(cfg: Config, plan: BuildPlan) -> None:
    """Render silhouettes + projection manifests for the building bodies and the segment pieces."""
    blender = find_blender(cfg)
    views = plan.views or cfg.render.views
    seg_views = cfg.render.segmentViews
    models = _models(plan)
    segments = _segments(cfg, plan)
    if plan.only:  # anything the user asked for that isn't a body or a segment piece?
        known = {p.stem for p in models} | {j.name for j in segments}
        missing = plan.only - known
        if missing:
            raise StageError(f"--only not found: {', '.join(sorted(missing))}")
    if not models and not segments:
        raise StageError(f"nothing to render in {MODELS_DIR}.")
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
        body_args = [
            *_common_args(cfg, glb, views),
            *_prepare_arg("--clearance", PREPARE_DIR / "clearance.json"),
            *_prepare_arg("--ports", PREPARE_DIR / "ports.json"),
            *_prepare_arg("--mesh-offsets", PREPARE_DIR / "mesh_offsets.json"),
        ]
        _invoke(blender, name, body_args)
        rendered += 1

    for job in segments:
        if not plan.force and not _needs_render(job.name, seg_views):
            C.console.print(f"[dim]skip[/] {job.name} (up to date; --force to redo)")
            continue
        C.rule(f"{job.name}  ({len(seg_views)} views)")
        glb = SEGMENTS_DIR / f"{job.source}.glb"
        _invoke(blender, job.name, [*_common_args(cfg, glb, seg_views), *_segment_args(job)])
        rendered += 1

    C.console.print(f"\n[green]Render complete[/] -> {RENDER_DIR}  ({rendered} rendered)")
