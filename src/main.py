"""The ``sat`` CLI entrypoint.

Two pipeline commands: ``extract`` (the only game-reliant step) and ``build`` (everything after
it). ``build`` currently runs the Blender raster stage; later stages fill in behind it. Plus the
dev helpers ``check`` / ``fix``.
"""

from __future__ import annotations

import subprocess
import sys

import typer

from src.cli import console as C
from src.cli.doctor import run_doctor

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Satisfactory buildings -> true-to-scale orthographic blueprint SVGs/PNGs.",
)


@app.command()
def doctor(
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Run the safe remediations (downloads, brew installs) after confirming.",
    ),
) -> None:
    """Check this machine and (optionally) install what's missing."""
    raise typer.Exit(run_doctor(fix=fix))


def _ruff(args: list[str]) -> int:
    return subprocess.run([sys.executable, "-m", "ruff", *args], check=False).returncode


@app.command()
def check() -> None:
    """Lint + format-check (ruff). CSharpier is wired in during Phase 3."""
    rc = _ruff(["check", "."])
    rc |= _ruff(["format", "--check", "."])
    raise typer.Exit(1 if rc else 0)


@app.command()
def fix() -> None:
    """Auto-fix lint + reformat (ruff)."""
    rc = _ruff(["check", "--fix", "."])
    rc |= _ruff(["format", "."])
    raise typer.Exit(1 if rc else 0)


@app.command()
def extract(
    only: list[str] = typer.Option(
        None,
        "--only",
        help="Extract only these building name(s) (repeatable); skips segments/connectors.",
    ),
    skip_segments: bool = typer.Option(
        False, "--skip-segments", help="Skip belt/pipe/beam/junction tiles."
    ),
    skip_connectors: bool = typer.Option(
        False, "--skip-connectors", help="Skip shared mouth-plate meshes."
    ),
    skip_ports: bool = typer.Option(False, "--skip-ports", help="Skip the --dump-ports pass."),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Force a rebuild of the sf-extract Docker image."
    ),
    find: str | None = typer.Option(
        None,
        "--find",
        help="Discovery mode: list mounted asset paths containing this substring, then exit.",
    ),
) -> None:
    """Extract meshes + port data from the Satisfactory install into build/01-extract/."""
    from src.cli.config import ConfigError, load_config
    from src.extract.run import ExtractError, ExtractPlan, find_assets, run_extract

    try:
        cfg = load_config()
        if find is not None:
            find_assets(cfg, find, rebuild=rebuild)
            return
        run_extract(
            cfg,
            ExtractPlan(
                only=set(only or []),
                skip_segments=skip_segments,
                skip_connectors=skip_connectors,
                skip_ports=skip_ports,
                rebuild=rebuild,
            ),
        )
    except (ExtractError, ConfigError) as exc:
        C.err_console.print(f"[red]extract failed:[/] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def build(
    theme: str = typer.Option(
        None,
        "--theme",
        help="Theme name (-> themes/<name>.yaml) or path to a theme file (default: from config).",
    ),
    only: list[str] = typer.Option(None, "--only", help="Build only these building(s)."),
    views: str = typer.Option(None, "--views", help="Comma-separated view override."),
    force: bool = typer.Option(False, "--force", help="Redo work even if outputs exist."),
    png: bool = typer.Option(False, "--png", help="Also rasterize each SVG to PNG (rsvg-convert)."),
    from_stage: str = typer.Option(None, "--from", help="[adv] Resume the pipeline at this stage."),
    stage: str = typer.Option(None, "--stage", help="[adv] Run just this one stage."),
) -> None:
    """Turn extracted models into schematics: everything after extract.

    Runs the pipeline stages in order (prepare -> render -> ...). Each stage lives in ``src/`` and
    is individually runnable via ``--stage``/``--from``; usually you just ``build --theme T``.
    """
    from src.cli.config import ConfigError, load_config
    from src.common.plan import BuildPlan, StageError
    from src.pipeline import run_build

    try:
        cfg = load_config()
        plan = BuildPlan(
            theme=theme or cfg.render.defaultTheme,
            only=set(only or []),
            views=[v.strip() for v in views.split(",")] if views else None,
            force=force,
            png=png,
            from_stage=from_stage,
            only_stage=stage,
        )
        run_build(cfg, plan)
    except (StageError, ConfigError) as exc:
        C.err_console.print(f"[red]build failed:[/] {exc}")
        raise typer.Exit(1) from exc


def main() -> None:
    """Console-script + ``python -m`` entrypoint. Forces the program name to ``sat``."""
    app(prog_name="sat")


if __name__ == "__main__":
    main()
