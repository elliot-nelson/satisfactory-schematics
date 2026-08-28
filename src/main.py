"""The ``sat`` CLI entrypoint.

Implemented so far: ``doctor``, ``extract`` (plus the dev helpers ``check`` / ``fix``). The
remaining pipeline stage commands are stubs that will be filled in during later phases.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

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


_STAGES = ["prepare", "render", "finalize", "preview", "bundle", "build"]


def _stub(name: str) -> None:
    C.err_console.print(
        f"[yellow]'{name}' is not implemented yet[/] (planned in NEW_REPO_PLAN.md). "
        "Current focus: Phase 0 + doctor."
    )
    raise typer.Exit(2)


def _make_stub(name: str) -> Callable[[], None]:
    def cmd() -> None:
        _stub(name)

    cmd.__name__ = name
    return cmd


for _stage in _STAGES:
    app.command(name=_stage, help=f"[stub] {_stage} stage (not implemented yet).")(
        _make_stub(_stage)
    )


def main() -> None:
    """Console-script + ``python -m`` entrypoint. Forces the program name to ``sat``."""
    app(prog_name="sat")


if __name__ == "__main__":
    main()
