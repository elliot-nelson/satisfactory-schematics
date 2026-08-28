"""The ``sat`` CLI entrypoint.

Only ``doctor`` (and the dev helpers ``check`` / ``fix``) are implemented for now; the
pipeline stage commands are stubs that will be filled in during later phases.
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


_STAGES = ["extract", "prepare", "render", "finalize", "preview", "bundle", "build"]


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
