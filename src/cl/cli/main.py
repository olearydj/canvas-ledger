"""Main CLI application for canvas-ledger.

Provides the root Typer application with version flag and error handling.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import typer

from cl import __version__

# Create main application
app: typer.Typer = typer.Typer(
    name="cl",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
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

    Build a durable historical record of your Canvas courses, enrollments,
    and roles. Answer questions that Canvas itself cannot easily answer:
    \b
    • What courses have I taught or taken, and when?
    • What was a student's enrollment history across my courses?
    • Who was the lead instructor for a co-taught course?
    • How did enrollment change over time (adds, drops)?
    • How did a student perform across multiple courses?

    Data is stored locally in SQLite. Canvas is read-only—this tool never
    modifies your Canvas data. You can annotate records with "declared truth"
    (like who was really the lead instructor) without changing what Canvas reports.
    \b
    Getting Started:
      1. cl config init        Configure Canvas URL and API token
      2. cl db migrate         Initialize the local database
      3. cl ingest catalog     Fetch all your Canvas courses
      4. cl query my-timeline  See your involvement history
    """
    pass


# Re-export output utilities for backward compatibility
from cl.cli.output import cli_error, cli_success, cli_warning

__all__ = ["app", "cli_error", "cli_success", "cli_warning"]

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
