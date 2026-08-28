"""Shared rich console + small helpers for status output and prompts."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm

console = Console()
err_console = Console(stderr=True)


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question. Non-interactive terminals fall back to ``default``."""
    if not console.is_interactive:
        return default
    return Confirm.ask(question, default=default, console=console)


def rule(title: str) -> None:
    console.rule(f"[bold]{title}")
