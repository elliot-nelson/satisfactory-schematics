"""The ``build`` pipeline: the ordered stages that turn ``build/01-extract/`` into finished
schematics, plus the driver that runs them.

Stages are deliberately small and independently runnable (each is a plain ``run(cfg, plan)``
function in its own ``src/<stage>/`` package). ``build`` runs them in order; the ``--from`` /
``--stage`` advanced flags let you resume from or isolate a single stage using existing artifacts.

Only ``prepare`` and ``render`` exist today; ``annotate`` -> ``finalize`` -> ``preview`` ->
``bundle`` slot in here as later phases land.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.cli import console as C
from src.cli.config import Config
from src.common.plan import BuildPlan, StageError
from src.prepare import run as prepare_run
from src.render import run as render_run


@dataclass(frozen=True)
class Stage:
    name: str
    summary: str
    run: Callable[[Config, BuildPlan], None]
    theme_dependent: bool = False  # theme-dependent stages are cheap and rerun per --theme


STAGES: list[Stage] = [
    Stage("prepare", "game data -> JSON contracts", prepare_run.run),
    Stage("render", "Blender rasters (theme-independent)", render_run.run),
]

STAGE_NAMES = [s.name for s in STAGES]


def _select(plan: BuildPlan) -> list[Stage]:
    """Resolve which stages to run from --stage / --from (mutually exclusive)."""
    choices = ", ".join(STAGE_NAMES)
    if plan.only_stage:
        if plan.only_stage not in STAGE_NAMES:
            raise StageError(f"unknown --stage '{plan.only_stage}'. Choices: {choices}")
        return [s for s in STAGES if s.name == plan.only_stage]
    if plan.from_stage:
        if plan.from_stage not in STAGE_NAMES:
            raise StageError(f"unknown --from '{plan.from_stage}'. Choices: {choices}")
        start = STAGE_NAMES.index(plan.from_stage)
        return STAGES[start:]
    return STAGES


def run_build(cfg: Config, plan: BuildPlan) -> None:
    """Run the selected pipeline stages in order."""
    if plan.only_stage and plan.from_stage:
        raise StageError("--stage and --from are mutually exclusive.")
    stages = _select(plan)
    total = len(stages)
    for i, stage in enumerate(stages, 1):
        C.rule(f"[{i}/{total}] {stage.name}  —  {stage.summary}")
        stage.run(cfg, plan)
    C.console.print(f"\n[bold green]Build complete[/] ({total} stage{'s' if total != 1 else ''}).")
