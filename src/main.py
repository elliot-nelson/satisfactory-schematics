"""The ``schematic`` CLI entrypoint.

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
    all_themes: bool = typer.Option(
        False,
        "--all-themes",
        help="Build every theme in themes/ in turn (incompatible with --theme).",
    ),
    only: list[str] = typer.Option(None, "--only", help="Build only these building(s)."),
    views: str = typer.Option(None, "--views", help="Comma-separated view override."),
    force: bool = typer.Option(False, "--force", help="Redo work even if outputs exist."),
    from_stage: str = typer.Option(None, "--from", help="[adv] Resume the pipeline at this stage."),
    stage: str = typer.Option(None, "--stage", help="[adv] Run just this one stage."),
) -> None:
    """Turn extracted models into schematics: everything after extract.

    Runs the pipeline stages in order (prepare -> render -> ...). Each stage lives in ``src/`` and
    is individually runnable via ``--stage``/``--from``; usually you just ``build --theme T``.
    """
    from src.cli.config import ConfigError, load_config
    from src.common.plan import BuildPlan, StageError
    from src.common.theme import ThemeError, select_themes
    from src.pipeline import run_build

    try:
        cfg = load_config()
        themes = select_themes(theme, all_themes, default=cfg.render.defaultTheme)
        for i, t in enumerate(themes, 1):
            if all_themes:
                C.rule(f"[bold cyan]theme {i}/{len(themes)}: {t}")
            plan = BuildPlan(
                theme=t,
                only=set(only or []),
                views=[v.strip() for v in views.split(",")] if views else None,
                force=force,
                from_stage=from_stage,
                only_stage=stage,
            )
            run_build(cfg, plan)
    except (StageError, ConfigError, ThemeError) as exc:
        C.err_console.print(f"[red]build failed:[/] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def upload(
    version: str = typer.Option(..., "--version", help="Version, e.g. 0.1.0 (tag: v0.1.0)."),
    theme: str = typer.Option(None, "--theme", help="Theme name/path whose built zip to publish."),
    all_themes: bool = typer.Option(
        False,
        "--all-themes",
        help="Upload every theme in themes/ to the same release (incompatible with --theme).",
    ),
) -> None:
    """Attach built deliverable zip(s) to a GitHub Release (tag ``v<version>``).

    Uploads ``dist/<theme>/<theme>.zip`` as ``<theme>-<version>.zip``. The first upload for a
    version creates the release pinned to HEAD's sha; later uploads (other themes, or re-runs) just
    attach to the same release page. Requires the ``gh`` CLI and that HEAD is already pushed.
    """
    from src.common.theme import ThemeError, select_themes
    from src.publish.upload import UploadError
    from src.publish.upload import run as upload_run

    try:
        for t in select_themes(theme, all_themes):
            upload_run(t, version)
    except (UploadError, ThemeError) as exc:
        C.err_console.print(f"[red]upload failed:[/] {exc}")
        raise typer.Exit(1) from exc


def main() -> None:
    """Console-script + ``python -m`` entrypoint. Forces the program name to ``schematic``."""
    app(prog_name="schematic")


if __name__ == "__main__":
    main()
