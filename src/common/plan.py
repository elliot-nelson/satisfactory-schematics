"""The shared ``BuildPlan`` passed to every ``build`` stage.

Lives in ``common`` (not ``pipeline``) so both the orchestrator and the individual stage modules
can import it without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class StageError(Exception):
    """A user-actionable failure in a build stage (missing input, bad data, tool missing)."""


@dataclass
class BuildPlan:
    """Options threaded through the whole post-extract pipeline.

    theme:      which theme's look to finalize (later stages).
    only:       limit work to these building names (empty == all).
    views:      override the config view list (None == config default).
    force:      redo work even when up-to-date outputs already exist.
    from_stage: (advanced) start the pipeline at this stage, reusing earlier build/ artifacts.
    only_stage: (advanced) run just this one stage.
    """

    theme: str
    only: set[str] = field(default_factory=set)
    views: list[str] | None = None
    force: bool = False
    from_stage: str | None = None
    only_stage: str | None = None

    def wants(self, name: str) -> bool:
        """True if a building name is in scope for this plan."""
        return not self.only or name in self.only
