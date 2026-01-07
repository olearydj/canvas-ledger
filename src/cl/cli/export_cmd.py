"""Export commands for canvas-ledger CLI.

Provides commands for exporting data in structured formats.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer

from cl.cli.output import cli_error
from cl.config.settings import load_settings
from cl.export.formatters import format_output
from cl.ledger.queries import (
    get_offering_by_canvas_id,
    get_offering_roster,
    get_offerings_with_terms,
    get_person_by_canvas_id,
    get_person_history,
)

app = typer.Typer(
    name="export",
    help="Export data in JSON or CSV for use by other tools. Output goes to stdout for piping to files or other commands.",
    no_args_is_help=True,
)


class ExportFormat(str, Enum):
    """Export format options."""

    json = "json"
    csv = "csv"


@app.command("offerings")
def offerings(
    fmt: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = ExportFormat.json,
) -> None:
    """Export all offerings with term information.

    Outputs your complete course catalog: Canvas ID, name, code, term, dates.
    Useful for creating course inventories or feeding data to other systems.
    \b
    Examples:
      cl export offerings > courses.json
      cl export offerings --format csv > courses.csv
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(
            f"Database not found at {settings.db_path}. "
            "Run 'cl db migrate' to initialize, then 'cl ingest catalog' to populate."
        )

    data = get_offerings_with_terms(settings.db_path)

    if not data:
        typer.echo("No offerings found. Run 'cl ingest catalog' first.", err=True)
        return

    # Define headers for CSV output
    headers = [
        "canvas_course_id",
        "name",
        "code",
        "workflow_state",
        "term_name",
        "term_start_date",
        "term_end_date",
        "observed_at",
        "last_seen_at",
    ]

    format_output(data, fmt=fmt.value, headers=headers)


@app.command("enrollments")
def enrollments(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    fmt: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = ExportFormat.json,
) -> None:
    """Export enrollment roster for an offering.

    Exports all enrollments for the specified offering, including
    person name, section, role, enrollment state, and grades.

    Requires deep ingestion: run 'cl ingest offering <id>' first.

    Examples:
        cl export enrollments 12345
        cl export enrollments 12345 --format csv
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' to initialize.")

    # Check if offering exists
    offering = get_offering_by_canvas_id(settings.db_path, offering_id)
    if offering is None:
        cli_error(
            f"Offering {offering_id} not found in local ledger. "
            "Run 'cl ingest catalog' to fetch courses."
        )

    # Get roster
    roster = get_offering_roster(settings.db_path, offering_id)
    if roster is None or not roster.sections:
        cli_error(
            f"No enrollment data for offering {offering_id}. "
            "Run 'cl ingest offering <id>' to fetch enrollments."
        )

    # Flatten roster into list of enrollment dicts
    rows = []
    for _section_name, entries in roster.sections.items():
        for entry in entries:
            rows.append(
                {
                    "canvas_course_id": offering_id,
                    "offering_name": roster.offering_name,
                    "section_name": entry.section_name,
                    "section_canvas_id": entry.section_canvas_id,
                    "canvas_user_id": entry.canvas_user_id,
                    "person_name": entry.person_name,
                    "sortable_name": entry.sortable_name,
                    "role": entry.role,
                    "enrollment_state": entry.enrollment_state,
                    "current_grade": entry.current_grade,
                    "current_score": entry.current_score,
                    "final_grade": entry.final_grade,
                    "final_score": entry.final_score,
                }
            )

    headers = [
        "canvas_course_id",
        "section_name",
        "canvas_user_id",
        "person_name",
        "sortable_name",
        "role",
        "enrollment_state",
        "current_grade",
        "current_score",
        "final_grade",
        "final_score",
    ]

    format_output(rows, fmt=fmt.value, headers=headers)


@app.command("person")
def person(
    person_id: Annotated[
        int,
        typer.Argument(help="Canvas user ID of the person."),
    ],
    fmt: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Output format.",
        ),
    ] = ExportFormat.json,
) -> None:
    """Export enrollment history for a person.

    Exports all enrollments for the specified person across offerings
    that have been deep-ingested, including offering, term, section,
    role, enrollment state, and grades.

    Examples:
        cl export person 12345
        cl export person 12345 --format csv
    """
    settings = load_settings()

    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' to initialize.")

    # Check if person exists
    person_record = get_person_by_canvas_id(settings.db_path, person_id)
    if person_record is None:
        cli_error(
            f"Person {person_id} not found in local ledger. "
            "Run 'cl ingest offering <id>' to fetch enrollment data."
        )

    # Get enrollment history
    history = get_person_history(settings.db_path, person_id)

    if not history:
        cli_error(f"No enrollment data for person {person_id}.")

    # Convert to export format
    rows = []
    for entry in history:
        rows.append(
            {
                "canvas_user_id": person_id,
                "person_name": person_record.name,
                "sortable_name": person_record.sortable_name,
                "canvas_course_id": entry.canvas_course_id,
                "offering_name": entry.offering_name,
                "offering_code": entry.offering_code,
                "term_name": entry.term_name,
                "term_start_date": (
                    entry.term_start_date.isoformat() if entry.term_start_date else None
                ),
                "section_name": entry.section_name,
                "section_canvas_id": entry.section_canvas_id,
                "role": entry.role,
                "enrollment_state": entry.enrollment_state,
                "current_grade": entry.current_grade,
                "current_score": entry.current_score,
                "final_grade": entry.final_grade,
                "final_score": entry.final_score,
            }
        )

    headers = [
        "canvas_user_id",
        "person_name",
        "canvas_course_id",
        "offering_name",
        "term_name",
        "section_name",
        "role",
        "enrollment_state",
        "current_grade",
        "current_score",
        "final_grade",
        "final_score",
    ]

    format_output(rows, fmt=fmt.value, headers=headers)
