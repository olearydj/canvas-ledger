"""CLI output utilities for canvas-ledger.

Provides consistent error, success, and warning message formatting.
"""

from __future__ import annotations

from typing import Never

import typer


def cli_error(message: str, exit_code: int = 1) -> Never:
    """Print error message to stderr and exit."""
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(exit_code)


def cli_success(message: str) -> None:
    """Print success message."""
    typer.secho(message, fg=typer.colors.GREEN)


def cli_warning(message: str) -> None:
    """Print warning message."""
    typer.secho(f"Warning: {message}", fg=typer.colors.YELLOW, err=True)
