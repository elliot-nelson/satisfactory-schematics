"""Shared rich console + small helpers for status output and prompts."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm

# highlight=False disables Rich's automatic repr-highlighter. We only ever colour output with
# explicit markup ([green], [dim], ...), and the auto-highlighter otherwise mangles things like
# "200x320 px" -- it reads the "0x320" as a hex literal and paints just that slice as a number.
console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question. Non-interactive terminals fall back to ``default``."""
    if not console.is_interactive:
        return default
    return Confirm.ask(question, default=default, console=console)


def rule(title: str) -> None:
    console.rule(f"[bold]{title}")
