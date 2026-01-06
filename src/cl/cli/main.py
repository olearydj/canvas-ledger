"""Main CLI application for canvas-ledger.

Provides the root Typer application with version flag and error handling.
"""

from __future__ import annotations

import logging
from typing import Never

import typer

from cl import __version__

# Create main application
app: typer.Typer = typer.Typer(
    name="cl",
    help="canvas-ledger: A local, queryable ledger of Canvas LMS metadata.",
    no_args_is_help=True,
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"canvas-ledger (cl) version {__version__}")
        raise typer.Exit()


def verbose_callback(value: bool) -> None:
    """Enable verbose/debug output."""
    if value:
        # Configure root logger for debug output
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        # Also enable debug for cl modules specifically
        logging.getLogger("cl").setLevel(logging.DEBUG)


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose/debug output.",
        callback=verbose_callback,
        is_eager=True,
    ),
) -> None:
    """canvas-ledger: A local, queryable ledger of Canvas LMS metadata.

    Maintain a durable historical record of your Canvas involvement,
    enrollments, and related metadata for answering questions that
    Canvas cannot easily answer.
    """
    pass


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


# Import and register command groups
# These imports are at the bottom to avoid circular imports
from cl.cli import annotate_cmd, config_cmd, db_cmd, export_cmd, ingest_cmd, query_cmd  # noqa: E402

app.add_typer(config_cmd.app, name="config")
app.add_typer(db_cmd.app, name="db")
app.add_typer(ingest_cmd.app, name="ingest")  # type: ignore[has-type]
app.add_typer(query_cmd.app, name="query")  # type: ignore[has-type]
app.add_typer(export_cmd.app, name="export")  # type: ignore[has-type]
app.add_typer(annotate_cmd.app, name="annotate")  # type: ignore[has-type]


if __name__ == "__main__":
    app()
