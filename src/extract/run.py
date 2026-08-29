"""Host-side driver for the containerized ``sf-extract`` .NET CLI.

Builds the Docker image (once), then runs it over the catalog to produce, under
``build/01-extract/``:

    models/<name>.glb              building bodies (+ extracted.json)
    models/segments/<name>.glb     belt/pipe/beam/junction tiles
    models/connectors/<name>.glb   shared belt/pipe mouth plates
    ports.raw.json                 raw connection + component transforms (--dump-ports)
    docs/en-US.json                copy of the game docs dump (clearance source for `prepare`)

The single game-touching stage: the install is mounted read-only, and the one game file the rest
of the pipeline needs (the docs dump) is copied out here -- so everything downstream reads only
build/01-extract/, never the install.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.cli import console as C
from src.cli.config import Config
from src.cli.context import EXTRACT_DIR, REPO_ROOT, ensure
from src.cli.doctor import resolve_game_dir
from src.common.buildings import Building, Catalog, load_catalog

IMAGE = "sf-extract"
DOTNET_DIR = Path(__file__).resolve().parent / "dotnet"
DOCKERFILE = DOTNET_DIR / "Dockerfile"
# The image builds from the repo root (app in src/, dependency in vendor/); see the Dockerfile.
OODLE_IN_IMAGE = "/opt/nativelibs/liboodle-data-shared.so"


class ExtractError(Exception):
    """Raised for user-actionable extraction failures (bad game path, docker, etc.)."""


@dataclass
class ExtractPlan:
    """What to run this invocation."""

    only: set[str] = field(default_factory=set)
    skip_segments: bool = False
    skip_connectors: bool = False
    skip_ports: bool = False
    rebuild: bool = False


# --------------------------------------------------------------------------------------
# Docker helpers
# --------------------------------------------------------------------------------------


def _docker_ok() -> None:
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        raise ExtractError(
            "Docker is not available/running. Run `./schematic doctor` (it can install Docker), "
            "then start Docker Desktop."
        )


def _image_exists() -> bool:
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            capture_output=True,
        ).returncode
        == 0
    )


def build_image(*, rebuild: bool = False) -> None:
    """Build the sf-extract image if it's missing (or ``rebuild`` forces it)."""
    _docker_ok()
    if _image_exists() and not rebuild:
        return
    C.console.print(
        f"[bold]Building {IMAGE} image[/] (first run or --rebuild; this takes a few min)..."
    )
    cmd = [
        "docker", "build", "--platform=linux/amd64",
        "-t", IMAGE,
        "-f", str(DOCKERFILE),
        str(REPO_ROOT),
    ]  # fmt: skip
    if rebuild:
        cmd.insert(2, "--no-cache")  # avoid COPY-layer staleness (SPEC.md 6)
    if subprocess.run(cmd).returncode != 0:
        raise ExtractError("docker build failed (see output above).")


def _docker_run(game_dir: Path, sub_args: list[str], *, quiet_stdout: bool) -> str:
    """Run one sf-extract pass. Streams stderr (progress); returns captured stdout."""
    cmd = [
        "docker", "run", "--rm", "--platform=linux/amd64",
        "-v", f"{game_dir}:/game:ro",
        "-v", f"{EXTRACT_DIR.resolve()}:/out",
        IMAGE,
        "--game-dir", "/game",
        "--oodle", OODLE_IN_IMAGE,
        *sub_args,
    ]  # fmt: skip
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE)
    if proc.returncode != 0:
        raise ExtractError(f"sf-extract failed (exit {proc.returncode}) for: {' '.join(sub_args)}")
    out = proc.stdout or ""
    if out and not quiet_stdout:
        C.console.print(out.rstrip())
    return out


# --------------------------------------------------------------------------------------
# List-file generation (catalog -> sf-extract's "assetPath = name" format)
# --------------------------------------------------------------------------------------


def _write_list(name: str, lines: list[str]) -> Path:
    lists_dir = ensure(EXTRACT_DIR / "_lists")
    path = lists_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mesh_lines(items: list) -> list[str]:
    return [f"{it.mesh} = {it.name}" for it in items]


# --------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------


def _game_dir(cfg: Config) -> Path:
    game_dir, source = resolve_game_dir(cfg)
    if game_dir is None or not game_dir.is_dir():
        raise ExtractError(
            "No valid Satisfactory install resolved. Run `./schematic doctor` to locate/configure it."
        )
    if source in ("config-missing", "env-missing"):
        raise ExtractError(
            f"Configured game path does not exist: {game_dir}. Fix it or run `./schematic doctor`."
        )
    return game_dir


def find_assets(cfg: Config, needle: str, *, rebuild: bool = False) -> None:
    """Discovery mode: list mounted asset paths containing ``needle`` (asset paths drift)."""
    build_image(rebuild=rebuild)
    game_dir = _game_dir(cfg)
    ensure(EXTRACT_DIR)
    _docker_run(game_dir, ["--out", "/out", "--find", needle], quiet_stdout=False)


def _selected_buildings(catalog: Catalog, only: set[str]) -> list[Building]:
    if not only:
        return catalog.buildings
    known = {b.name for b in catalog.buildings}
    unknown = only - known
    if unknown:
        raise ExtractError(f"--only names not in buildings.yaml: {', '.join(sorted(unknown))}")
    return [b for b in catalog.buildings if b.name in only]


def run_extract(cfg: Config, plan: ExtractPlan) -> None:
    """Run the full extraction (or a subset per ``plan``)."""
    catalog = load_catalog(cfg)
    build_image(rebuild=plan.rebuild)
    game_dir = _game_dir(cfg)
    ensure(EXTRACT_DIR)

    buildings = _selected_buildings(catalog, plan.only)
    targeted = bool(plan.only)  # a targeted run skips the unrelated segment/connector sets

    # 1) building bodies -> models/
    C.rule(f"Buildings ({len(buildings)})")
    mesh_list = _write_list("buildings.txt", _mesh_lines(buildings))
    _docker_run(
        game_dir,
        ["--out", "/out/models", "--list", f"/out/_lists/{mesh_list.name}"],
        quiet_stdout=False,
    )

    # 2) segments -> models/segments/
    if catalog.segments and not plan.skip_segments and not targeted:
        C.rule(f"Segments ({len(catalog.segments)})")
        seg_list = _write_list("segments.txt", _mesh_lines(catalog.segments))
        _docker_run(
            game_dir,
            ["--out", "/out/models/segments", "--list", f"/out/_lists/{seg_list.name}"],
            quiet_stdout=False,
        )

    # 3) connectors -> models/connectors/
    if catalog.connectors and not plan.skip_connectors and not targeted:
        C.rule(f"Connectors ({len(catalog.connectors)})")
        con_list = _write_list("connectors.txt", _mesh_lines(catalog.connectors))
        _docker_run(
            game_dir,
            ["--out", "/out/models/connectors", "--list", f"/out/_lists/{con_list.name}"],
            quiet_stdout=False,
        )

    # 4) I/O ports + component transforms -> ports.raw.json (stdout is the full JSON: suppress)
    if not plan.skip_ports:
        C.rule(f"Ports dump ({len(buildings)})")
        bp_list = _write_list("blueprints.txt", [b.blueprint for b in buildings])
        _docker_run(
            game_dir,
            ["--out", "/out", "--list", f"/out/_lists/{bp_list.name}", "--dump-ports"],
            quiet_stdout=True,
        )

    # 5) copy the game's docs dump so `prepare` (clearance) can run fully offline. This is the
    #    boundary: extract is the ONLY stage that reads the install -- everything downstream reads
    #    build/01-extract/.
    _copy_game_docs(game_dir)

    C.console.print(f"\n[green]Extraction complete[/] -> {EXTRACT_DIR}")


def _copy_game_docs(game_dir: Path) -> None:
    """Copy CommunityResources/Docs/en-US.json into build/01-extract/docs/ (clearance source)."""
    src = game_dir / "CommunityResources" / "Docs" / "en-US.json"
    if not src.is_file():
        C.err_console.print(f"[yellow]warning:[/] game docs not found at {src}")
        return
    dst = ensure(EXTRACT_DIR / "docs") / "en-US.json"
    shutil.copy2(src, dst)
    C.console.print(f"[dim]docs -> {dst.relative_to(REPO_ROOT)}[/]")
