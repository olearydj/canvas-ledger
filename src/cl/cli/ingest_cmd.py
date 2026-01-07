"""Ingest commands for canvas-ledger CLI.

Provides commands for ingesting data from Canvas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from cl.canvas.client import CanvasAuthenticationError, CanvasClient, CanvasClientError
from cl.cli.output import cli_error, cli_success, cli_warning
from cl.config.secrets import SecretProviderError, get_canvas_token
from cl.config.settings import Settings, load_settings
from cl.export.formatters import format_output
from cl.ledger.ingest import get_last_ingest_run, ingest_catalog, ingest_offering

if TYPE_CHECKING:
    pass

app = typer.Typer(
    name="ingest",
    help="""Ingest data from Canvas into the local ledger.

Ingestion has two levels:
\b
  CATALOG   'cl ingest catalog' fetches all courses visible to you—names,
            codes, terms, and your role. Fast and safe to run anytime.
  OFFERING  'cl ingest offering <id>' fetches full details for one course—
            sections, enrollments, grades. Use for courses you query deeply.

All ingestion is read-only and idempotent. Re-running updates records
and tracks changes ("drift") over time.
""",
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

    Fetches every course you can access (as teacher, TA, student, observer,
    etc.) along with term information and your observed roles.
    \b
    What this ingests:
      • Course metadata (name, code, workflow state)
      • Term associations
      • Your enrollment role(s) in each course
    \b
    What this does NOT ingest (use 'cl ingest offering' for these):
      • Other people's enrollments
      • Sections
      • Grades

    Idempotent: safe to run repeatedly. Re-runs detect and track changes.
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

    Fetches complete data for one course, enabling roster queries, person
    history, and grade tracking for that course.
    \b
    What this ingests:
      • All sections in the course
      • All enrollments (students, TAs, teachers, observers)
      • Person details (name, SIS ID)
      • Grades (current and final, where available)
    \b
    Prerequisites:
      • Run 'cl ingest catalog' first so the offering exists locally
      • Find the Canvas course ID: it's in the URL when viewing the course

    Idempotent: safe to run repeatedly. Re-runs detect add/drop changes
    and grade updates, tracked as "drift" in the change log.
    \b
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

    Displays information about the most recent ingestion run:
    timestamp, scope (catalog or offering), status, and record counts.

    Useful for verifying that ingestion completed successfully and
    reviewing what changed.
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
