"""Ingest commands for canvas-ledger CLI.

Provides commands for ingesting data from Canvas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from cl.canvas.client import CanvasAuthenticationError, CanvasClient, CanvasClientError
from cl.cli.main import cli_error, cli_success, cli_warning
from cl.config.secrets import SecretProviderError, get_canvas_token
from cl.config.settings import Settings, load_settings
from cl.export.formatters import format_output
from cl.ledger.ingest import get_last_ingest_run, ingest_catalog, ingest_offering

if TYPE_CHECKING:
    pass

app = typer.Typer(
    name="ingest",
    help="Ingest data from Canvas.",
    no_args_is_help=True,
)


def _get_canvas_client(settings: Settings) -> CanvasClient:
    """Create a Canvas client from settings."""
    try:
        token = get_canvas_token(
            provider_name=settings.secret_provider,
            op_reference=settings.op_reference,
        )
    except SecretProviderError as e:
        cli_error(str(e))

    if not settings.canvas_base_url:
        cli_error(
            "Canvas base URL not configured. "
            "Run 'cl config set canvas_base_url <url>' to configure."
        )

    return CanvasClient(settings.canvas_base_url, token)


@app.command("catalog")
def catalog(
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress detailed output.",
        ),
    ] = False,
) -> None:
    """Ingest all courses visible to you from Canvas.

    Fetches all courses you have access to (regardless of role: teacher,
    TA, student, observer, etc.) and stores them in the local ledger.

    This is idempotent: running it multiple times will update existing
    records and add new ones, but will not create duplicates.
    """
    settings = load_settings()

    # Validate settings
    errors = settings.validate()
    if errors:
        cli_error("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    # Ensure database exists
    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' first.")

    # Create Canvas client
    client = _get_canvas_client(settings)

    if not quiet:
        typer.echo("Fetching courses from Canvas...")

    try:
        result = ingest_catalog(client, settings.db_path)
    except CanvasAuthenticationError as e:
        cli_error(str(e))
    except CanvasClientError as e:
        cli_error(f"Canvas API error: {e}")

    if result.error:
        cli_error(f"Ingestion failed: {result.error}")

    # Report results
    if not quiet:
        cli_success("Catalog ingestion complete.")
        typer.echo(f"  New:       {result.new_count}")
        typer.echo(f"  Updated:   {result.updated_count}")
        typer.echo(f"  Unchanged: {result.unchanged_count}")
        typer.echo(f"  Total:     {result.total_count}")

        if result.drift_detected:
            cli_warning(f"Drift detected in {len(result.drift_detected)} record(s).")
            for drift in result.drift_detected[:5]:  # Show first 5
                typer.echo(f"    - {drift}")
            if len(result.drift_detected) > 5:
                typer.echo(f"    ... and {len(result.drift_detected) - 5} more")


@app.command("offering")
def offering_cmd(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering to deep ingest."),
    ],
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress detailed output.",
        ),
    ] = False,
) -> None:
    """Deep ingest a specific offering (sections, enrollments, people).

    Fetches all sections, enrollments (all roles), and person data for
    the specified offering and stores them in the local ledger.

    The offering must already exist locally (run 'cl ingest catalog' first).

    This is idempotent: running it multiple times will update existing
    records and add new ones, but will not create duplicates.

    Examples:
        cl ingest offering 12345
        cl ingest offering 12345 --quiet
    """
    settings = load_settings()

    # Validate settings
    errors = settings.validate()
    if errors:
        cli_error("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    # Ensure database exists
    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' first.")

    # Create Canvas client
    client = _get_canvas_client(settings)

    if not quiet:
        typer.echo(f"Deep ingesting offering {offering_id}...")

    try:
        result = ingest_offering(client, settings.db_path, offering_id)
    except CanvasAuthenticationError as e:
        cli_error(str(e))
    except CanvasClientError as e:
        cli_error(f"Canvas API error: {e}")

    if result.error:
        cli_error(f"Ingestion failed: {result.error}")

    # Report results
    if not quiet:
        cli_success(f"Deep ingestion complete for offering {offering_id}.")
        typer.echo(f"  New:       {result.new_count}")
        typer.echo(f"  Updated:   {result.updated_count}")
        typer.echo(f"  Unchanged: {result.unchanged_count}")
        typer.echo(f"  Total:     {result.total_count}")

        if result.drift_detected:
            cli_warning(f"Drift detected in {len(result.drift_detected)} record(s).")
            for drift in result.drift_detected[:5]:  # Show first 5
                typer.echo(f"    - {drift}")
            if len(result.drift_detected) > 5:
                typer.echo(f"    ... and {len(result.drift_detected) - 5} more")


@app.command("status")
def status(
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (table, json).",
        ),
    ] = "table",
) -> None:
    """Show the last ingestion run details.

    Displays information about the most recent ingestion run,
    including timestamp, scope, status, and counts.
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' first.")

    run = get_last_ingest_run(settings.db_path)

    if run is None:
        typer.echo("No ingestion runs found.")
        return

    data = run.to_dict()
    format_output(data, fmt=fmt)
