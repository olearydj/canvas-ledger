"""Query commands for canvas-ledger CLI.

Provides commands for querying the local ledger.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer

from cl.cli.main import cli_error
from cl.config.settings import load_settings
from cl.export.formatters import format_output
from cl.ledger.queries import (
    get_my_timeline,
    get_offering_by_canvas_id,
    get_offering_drift,
    get_offering_responsibility,
    get_offering_roster,
    get_person_by_canvas_id,
    get_person_drift,
    get_person_history,
)

app = typer.Typer(
    name="query",
    help="Query the local ledger.",
    no_args_is_help=True,
)


class OutputFormat(str, Enum):
    """Output format options."""

    json = "json"
    csv = "csv"
    table = "table"


@app.command("my-timeline")
def my_timeline(
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
    term: Annotated[
        str | None,
        typer.Option(
            "--term",
            "-t",
            help="Filter by term name (case-insensitive contains match).",
        ),
    ] = None,
    role: Annotated[
        str | None,
        typer.Option(
            "--role",
            "-r",
            help="Filter by role (exact match: teacher, ta, student, etc.).",
        ),
    ] = None,
) -> None:
    """Show your involvement timeline across all offerings.

    Displays all offerings you have enrollments in, sorted by term
    (most recent first). Shows your role(s) in each offering, along
    with any declared involvement annotations.

    This is the primary answer to: "What courses have I been involved in?"
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    entries = get_my_timeline(
        db_path=settings.db_path,
        term_filter=term,
        role_filter=role,
    )

    if not entries:
        if term or role:
            typer.echo("No offerings found matching the specified filters.")
        else:
            typer.echo("No offerings found. Run 'cl ingest catalog' to fetch your courses.")
        return

    # Convert to list of dicts for formatting
    data = [entry.to_dict() for entry in entries]

    # Define headers for table/CSV output (ordered subset of fields)
    # Include declared_involvement to show both observed and declared data
    headers = [
        "offering_name",
        "offering_code",
        "term_name",
        "observed_roles",
        "declared_involvement",
        "workflow_state",
    ]

    format_output(data, fmt=fmt.value, headers=headers)


@app.command("offering")
def offering(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    instructors: Annotated[
        bool,
        typer.Option(
            "--instructors",
            "-i",
            help="Show instructor responsibility information.",
        ),
    ] = False,
    roster: Annotated[
        bool,
        typer.Option(
            "--roster",
            "-r",
            help="Show full roster grouped by section (requires deep ingestion).",
        ),
    ] = False,
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
) -> None:
    """Query information about a specific offering.

    By default, shows basic offering information.
    Use --instructors to see who is responsible for the course.
    Use --roster to see the full enrollment roster grouped by section.

    Note: Roster information requires deep ingestion. Run
    'cl ingest offering <id>' first to populate enrollment data.

    Examples:
        cl query offering 12345
        cl query offering 12345 --instructors
        cl query offering 12345 --roster
        cl query offering 12345 --roster --format json
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    # First check if offering exists
    off = get_offering_by_canvas_id(settings.db_path, offering_id)
    if off is None:
        cli_error(
            f"Offering {offering_id} not found in local ledger. "
            "Run 'cl ingest catalog' to fetch courses."
        )

    if roster:
        # Show roster grouped by section
        roster_data = get_offering_roster(settings.db_path, offering_id)
        if roster_data is None:
            cli_error(f"Offering {offering_id} not found.")

        if not roster_data.sections:
            typer.echo(
                f"No enrollments found for offering {offering_id}.\n"
                "Run 'cl ingest offering <id>' to fetch enrollment data."
            )
            return

        if fmt == OutputFormat.json:
            format_output(roster_data.to_dict(), fmt="json")
        elif fmt == OutputFormat.csv:
            # Flatten for CSV - one row per enrollment
            rows = []
            for _section_name, entries in roster_data.sections.items():
                for entry in entries:
                    rows.append(entry.to_dict())
            headers = [
                "section_name",
                "person_name",
                "canvas_user_id",
                "role",
                "enrollment_state",
            ]
            format_output(rows, fmt="csv", headers=headers)
        else:
            # Table output - group by section
            typer.echo(f"Roster for: {roster_data.offering_name}")
            typer.echo(f"Code: {roster_data.offering_code or '(none)'}")
            typer.echo(f"Canvas ID: {roster_data.canvas_course_id}")
            typer.echo("")

            for section_name, entries in sorted(roster_data.sections.items()):
                typer.secho(f"Section: {section_name} ({len(entries)} enrollments)", bold=True)
                for entry in entries:
                    grade_info = ""
                    if entry.current_grade or entry.final_grade:
                        grade_info = f" [{entry.current_grade or entry.final_grade}]"
                    typer.echo(
                        f"  - {entry.person_name} ({entry.role}, {entry.enrollment_state}){grade_info}"
                    )
                typer.echo("")

    elif instructors:
        # Show instructor responsibility information
        resp = get_offering_responsibility(settings.db_path, offering_id)
        if resp is None:
            cli_error(f"Could not get responsibility info for offering {offering_id}.")

        if fmt == OutputFormat.json:
            format_output(resp.to_dict(), fmt="json")
        elif fmt == OutputFormat.csv:
            # Flatten for CSV
            rows = []
            for inst in resp.observed_instructors:
                rows.append(
                    {
                        "canvas_course_id": resp.canvas_course_id,
                        "offering_name": resp.offering_name,
                        "canvas_user_id": inst.get("canvas_user_id", ""),
                        "person_name": inst.get("person_name", "(your enrollment)"),
                        "role": inst["role"],
                        "enrollment_state": inst["enrollment_state"],
                        "source": inst["source"],
                        "is_declared_lead": "yes"
                        if resp.declared_lead
                        and inst.get("canvas_user_id") == resp.declared_lead.get("person_canvas_id")
                        else "no",
                    }
                )
            if not rows:
                rows = [
                    {
                        "canvas_course_id": resp.canvas_course_id,
                        "offering_name": resp.offering_name,
                        "note": "No instructors found",
                    }
                ]
            format_output(rows, fmt="csv")
        else:
            # Table output
            typer.echo(f"Offering: {resp.offering_name}")
            typer.echo(f"Code: {resp.offering_code or '(none)'}")
            typer.echo(f"Canvas ID: {resp.canvas_course_id}")
            typer.echo("")

            typer.secho("Observed Instructors:", bold=True)
            if resp.observed_instructors:
                for inst in resp.observed_instructors:
                    name = inst.get("person_name", "(your enrollment)")
                    user_id = inst.get("canvas_user_id", "")
                    if user_id:
                        typer.echo(
                            f"  - {name} (ID: {user_id}) - {inst['role']}, {inst['enrollment_state']}"
                        )
                    else:
                        typer.echo(f"  - Role: {inst['role']}, State: {inst['enrollment_state']}")
            else:
                typer.echo("  (none - run 'cl ingest offering' to fetch instructor enrollments)")
            typer.echo("")

            typer.secho("Declared Lead:", bold=True)
            if resp.declared_lead:
                person_name = resp.declared_lead.get("person_name", "(unknown)")
                typer.echo(f"  {person_name} (ID: {resp.declared_lead['person_canvas_id']})")
                typer.echo(f"  Designation: {resp.declared_lead['designation']}")
                typer.echo(f"  Added: {resp.declared_lead['created_at']}")
            else:
                typer.echo("  (not set - use 'cl annotate lead' to declare)")
    else:
        # Show basic offering info
        data = off.to_dict()
        if fmt == OutputFormat.json:
            format_output(data, fmt="json")
        elif fmt == OutputFormat.csv:
            format_output([data], fmt="csv")
        else:
            typer.echo(f"Name: {off.name}")
            typer.echo(f"Code: {off.code or '(none)'}")
            typer.echo(f"Canvas ID: {off.canvas_course_id}")
            typer.echo(f"Workflow State: {off.workflow_state}")
            typer.echo(
                f"Observed At: {off.observed_at.isoformat() if off.observed_at else '(unknown)'}"
            )
            typer.echo(
                f"Last Seen At: {off.last_seen_at.isoformat() if off.last_seen_at else '(unknown)'}"
            )


@app.command("person")
def person(
    person_id: Annotated[
        int,
        typer.Argument(help="Canvas user ID of the person."),
    ],
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
) -> None:
    """Query enrollment history for a person.

    Shows all enrollments for the specified person across offerings
    that have been deep-ingested. Sorted by term (most recent first).

    Note: This only shows data from offerings that have been deep-ingested.
    Run 'cl ingest offering <id>' for each offering you want to include.

    Examples:
        cl query person 12345
        cl query person 12345 --format json
        cl query person 12345 --format csv
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' to initialize.")

    # Check if person exists in ledger
    person_record = get_person_by_canvas_id(settings.db_path, person_id)
    if person_record is None:
        cli_error(
            f"Person {person_id} not found in local ledger.\n"
            "This person may not have been encountered during deep ingestion.\n"
            "Run 'cl ingest offering <id>' to fetch enrollment data for specific offerings."
        )

    # Get enrollment history
    history = get_person_history(settings.db_path, person_id)

    if not history:
        typer.echo(f"Person: {person_record.name}")
        typer.echo(f"Canvas User ID: {person_id}")
        typer.echo("")
        typer.echo("No enrollments found for this person.")
        return

    if fmt == OutputFormat.json:
        data = {
            "canvas_user_id": person_id,
            "person_name": person_record.name,
            "sortable_name": person_record.sortable_name,
            "enrollments": [entry.to_dict() for entry in history],
        }
        format_output(data, fmt="json")
    elif fmt == OutputFormat.csv:
        rows = [entry.to_dict() for entry in history]
        headers = [
            "offering_name",
            "offering_code",
            "term_name",
            "section_name",
            "role",
            "enrollment_state",
            "current_grade",
            "final_grade",
        ]
        format_output(rows, fmt="csv", headers=headers)
    else:
        # Table output
        typer.echo(f"Person: {person_record.name}")
        typer.echo(f"Canvas User ID: {person_id}")
        if person_record.sortable_name:
            typer.echo(f"Sortable Name: {person_record.sortable_name}")
        if person_record.sis_user_id:
            typer.echo(f"SIS User ID: {person_record.sis_user_id}")
        typer.echo("")

        typer.secho(f"Enrollment History ({len(history)} enrollments):", bold=True)
        typer.echo("")

        current_term = None
        for entry in history:
            term = entry.term_name or "(No Term)"
            if term != current_term:
                current_term = term
                typer.secho(f"  {term}", bold=True)

            grade_info = ""
            if entry.current_grade or entry.final_grade:
                grade = entry.final_grade or entry.current_grade
                grade_info = f" [Grade: {grade}]"

            section_info = f" ({entry.section_name})" if entry.section_name else ""
            typer.echo(
                f"    - {entry.offering_name}{section_info}\n"
                f"      {entry.role}, {entry.enrollment_state}{grade_info}"
            )


# =============================================================================
# Drift Subcommands
# =============================================================================


drift_app = typer.Typer(
    name="drift",
    help="Query change history (drift) for entities.",
    no_args_is_help=True,
)
app.add_typer(drift_app)


@drift_app.command("person")
def drift_person(
    person_id: Annotated[
        int,
        typer.Argument(help="Canvas user ID of the person."),
    ],
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
) -> None:
    """Query drift history for a person.

    Shows all recorded changes for the person and their enrollments
    across ingestion runs. Useful for understanding how a student's
    enrollment status or grades have changed over time.

    Examples:
        cl query drift person 12345
        cl query drift person 12345 --format json
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' to initialize.")

    drift = get_person_drift(settings.db_path, person_id)
    if drift is None:
        cli_error(
            f"Person {person_id} not found in local ledger.\n"
            "This person may not have been encountered during deep ingestion."
        )

    if fmt == OutputFormat.json:
        format_output(drift.to_dict(), fmt="json")
    elif fmt == OutputFormat.csv:
        if not drift.changes:
            typer.echo("No changes recorded for this person.")
            return
        rows = [c.to_dict() for c in drift.changes]
        headers = [
            "observed_at",
            "entity_type",
            "field_name",
            "old_value",
            "new_value",
            "ingest_run_id",
        ]
        format_output(rows, fmt="csv", headers=headers)
    else:
        # Table output
        typer.echo(f"Person: {drift.person_name}")
        typer.echo(f"Canvas User ID: {drift.canvas_user_id}")
        typer.echo("")

        if not drift.changes:
            typer.echo("No changes recorded for this person.")
            return

        typer.secho(f"Change History ({len(drift.changes)} changes):", bold=True)
        typer.echo("")

        for change in drift.changes:
            observed = change.observed_at.strftime("%Y-%m-%d %H:%M")
            typer.echo(
                f"  [{observed}] {change.entity_type}/{change.entity_canvas_id}: "
                f"{change.field_name}"
            )
            typer.echo(f"    '{change.old_value}' -> '{change.new_value}'")


@drift_app.command("offering")
def drift_offering(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = OutputFormat.table,
) -> None:
    """Query drift history for an offering.

    Shows all recorded changes for the offering, including its
    sections and enrollments across ingestion runs. Useful for
    tracking enrollment changes like adds, drops, and state transitions.

    Examples:
        cl query drift offering 12345
        cl query drift offering 12345 --format json
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' to initialize.")

    drift = get_offering_drift(settings.db_path, offering_id)
    if drift is None:
        cli_error(
            f"Offering {offering_id} not found in local ledger.\n"
            "Run 'cl ingest catalog' to fetch courses."
        )

    if fmt == OutputFormat.json:
        format_output(drift.to_dict(), fmt="json")
    elif fmt == OutputFormat.csv:
        if not drift.changes:
            typer.echo("No changes recorded for this offering.")
            return
        rows = [c.to_dict() for c in drift.changes]
        headers = [
            "observed_at",
            "entity_type",
            "entity_canvas_id",
            "field_name",
            "old_value",
            "new_value",
            "ingest_run_id",
        ]
        format_output(rows, fmt="csv", headers=headers)
    else:
        # Table output
        typer.echo(f"Offering: {drift.offering_name}")
        typer.echo(f"Code: {drift.offering_code or '(none)'}")
        typer.echo(f"Canvas ID: {drift.canvas_course_id}")
        typer.echo("")

        if not drift.changes:
            typer.echo("No changes recorded for this offering.")
            return

        typer.secho(f"Change History ({len(drift.changes)} changes):", bold=True)
        typer.echo("")

        for change in drift.changes:
            observed = change.observed_at.strftime("%Y-%m-%d %H:%M")
            typer.echo(
                f"  [{observed}] {change.entity_type}/{change.entity_canvas_id}: "
                f"{change.field_name}"
            )
            typer.echo(f"    '{change.old_value}' -> '{change.new_value}'")
