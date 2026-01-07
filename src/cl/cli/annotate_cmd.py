"""Annotate commands for canvas-ledger CLI.

Provides commands for managing annotations (declared truth).
"""

from __future__ import annotations

from typing import Annotated

import typer

from cl.annotations.manager import (
    AliasAlreadyExistsError,
    AliasNotFoundError,
    AnnotationError,
    OfferingAlreadyInAliasError,
    OfferingNotInAliasError,
    add_involvement,
    add_lead_instructor,
    add_to_alias,
    create_alias,
    delete_alias,
    get_alias_offerings,
    list_aliases,
    list_annotations,
    remove_annotation,
    remove_from_alias,
)
from cl.cli.output import cli_error, cli_success
from cl.config.settings import load_settings
from cl.export.formatters import format_output

app = typer.Typer(
    name="annotate",
    help="Manage annotations (your declared truth vs Canvas observed truth). Record corrections without changing what Canvas reports—both views are preserved.",
    no_args_is_help=True,
)


def _ensure_db_exists() -> None:
    """Ensure the database exists, or error out."""
    settings = load_settings()
    if not settings.db_path.exists():
        cli_error(f"Database not found at {settings.db_path}. Run 'cl db migrate' first.")


@app.command("lead")
def lead(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    person_id: Annotated[
        int,
        typer.Argument(help="Canvas user ID of the lead instructor."),
    ],
    designation: Annotated[
        str,
        typer.Option(
            "--designation",
            "-d",
            help="Designation type: 'lead' or 'grade_responsible'.",
        ),
    ] = "lead",
) -> None:
    """Declare the lead/grade-responsible instructor for an offering.

    Use when Canvas shows multiple instructors but doesn't indicate who
    was actually responsible for the course. This annotation is shown
    alongside observed Canvas roles in query output.
    \b
    Examples:
      cl annotate lead 12345 67890                    # Mark as lead
      cl annotate lead 12345 67890 -d grade_responsible
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        annotation = add_lead_instructor(
            settings.db_path,
            offering_canvas_id=offering_id,
            person_canvas_id=person_id,
            designation=designation,
        )
        cli_success(f"Lead instructor annotation added (ID: {annotation.id}).")
        typer.echo(f"  Offering: {annotation.offering_canvas_id}")
        typer.echo(f"  Person:   {annotation.person_canvas_id}")
        typer.echo(f"  Type:     {annotation.designation.value}")
    except AnnotationError as e:
        cli_error(str(e))
    except ValueError as e:
        cli_error(str(e))


@app.command("involvement")
def involvement(
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID of the offering."),
    ],
    classification: Annotated[
        str,
        typer.Argument(help="Involvement classification (e.g., 'developed course')."),
    ],
) -> None:
    """Classify your involvement in an offering.

    This annotation allows you to describe your actual involvement when
    the Canvas role doesn't tell the full story.

    Examples:
        cl annotate involvement 12345 "developed course"
        cl annotate involvement 12345 "guest lecturer"
        cl annotate involvement 12345 "course coordinator"
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        annotation = add_involvement(
            settings.db_path,
            offering_canvas_id=offering_id,
            classification=classification,
        )
        cli_success(f"Involvement annotation added (ID: {annotation.id}).")
        typer.echo(f"  Offering:       {annotation.offering_canvas_id}")
        typer.echo(f"  Classification: {annotation.classification}")
    except AnnotationError as e:
        cli_error(str(e))


@app.command("list")
def list_cmd(
    offering_id: Annotated[
        int | None,
        typer.Option(
            "--offering",
            "-o",
            help="Filter by Canvas course ID.",
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (table, json, csv).",
        ),
    ] = "table",
) -> None:
    """List annotations.

    By default, lists all annotations. Use --offering to filter by course.

    Examples:
        cl annotate list
        cl annotate list --offering 12345
        cl annotate list --format json
    """
    _ensure_db_exists()
    settings = load_settings()

    annotations = list_annotations(settings.db_path, offering_canvas_id=offering_id)

    if not annotations:
        if offering_id:
            typer.echo(f"No annotations found for offering {offering_id}.")
        else:
            typer.echo("No annotations found.")
        return

    # Format output
    if fmt == "table":
        # Custom table output for annotations
        typer.echo(f"{'ID':<6} {'Type':<16} {'Offering':<12} {'Details':<40}")
        typer.echo("-" * 76)
        for ann in annotations:
            ann_type = ann["annotation_type"]
            offering = str(ann["offering_canvas_id"])
            if ann_type == "lead_instructor":
                details = f"Person: {ann['person_canvas_id']}, {ann['designation']}"
            else:
                details = ann.get("classification", "")
            typer.echo(f"{ann['id']:<6} {ann_type:<16} {offering:<12} {details:<40}")
    else:
        format_output(annotations, fmt=fmt)


@app.command("remove")
def remove(
    annotation_id: Annotated[
        int,
        typer.Argument(help="ID of the annotation to remove."),
    ],
    annotation_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Type of annotation: 'lead_instructor' or 'involvement'.",
        ),
    ] = "lead_instructor",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-y",
            help="Skip confirmation prompt.",
        ),
    ] = False,
) -> None:
    """Remove an annotation by ID.

    Examples:
        cl annotate remove 1 --type lead_instructor
        cl annotate remove 2 --type involvement --force
    """
    _ensure_db_exists()
    settings = load_settings()

    # Confirm removal unless --force
    if not force:
        confirm = typer.confirm(f"Remove {annotation_type} annotation ID {annotation_id}?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit()

    try:
        remove_annotation(settings.db_path, annotation_id, annotation_type)
        cli_success(f"Annotation {annotation_id} removed.")
    except AnnotationError as e:
        cli_error(str(e))
    except ValueError as e:
        cli_error(str(e))


# =============================================================================
# Alias subcommands (Phase 6)
# =============================================================================

alias_app = typer.Typer(
    name="alias",
    help="""Manage course aliases (group related offerings under one name).

Aliases solve the "same course, different IDs" problem: course renumberings,
special topics taught as different courses, cross-listed courses.

Create an alias, add offerings to it, then query with 'cl query alias'.
""",
    no_args_is_help=True,
)
app.add_typer(alias_app)


@alias_app.command("create")
def alias_create(
    name: Annotated[
        str,
        typer.Argument(help="Name for the alias (e.g., 'BET 3510')."),
    ],
    offering_ids: Annotated[
        list[int] | None,
        typer.Argument(help="Optional Canvas course IDs to include initially."),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option(
            "--description",
            "-d",
            help="Optional description of the alias.",
        ),
    ] = None,
) -> None:
    """Create a new course alias.

    Course aliases allow you to group related offerings for unified queries.
    Use cases include:
    - Course renumbering (e.g., "CS 101" became "COMP 1010")
    - Special topics variations
    - Local naming conventions

    Examples:
        cl annotate alias create "BET 3510"
        cl annotate alias create "Intro Programming" 12345 67890
        cl annotate alias create "Data Structures" --description "All DS offerings"
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        alias = create_alias(
            settings.db_path,
            name=name,
            offering_canvas_ids=offering_ids,
            description=description,
        )
        cli_success(f"Alias '{name}' created (ID: {alias.id}).")
        if offering_ids:
            typer.echo(f"  Includes {len(offering_ids)} offering(s).")
        if description:
            typer.echo(f"  Description: {description}")
    except AliasAlreadyExistsError as e:
        cli_error(str(e))
    except AnnotationError as e:
        cli_error(str(e))


@alias_app.command("add")
def alias_add(
    name: Annotated[
        str,
        typer.Argument(help="Name of the existing alias."),
    ],
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID to add to the alias."),
    ],
) -> None:
    """Add an offering to an existing alias.

    Examples:
        cl annotate alias add "BET 3510" 12345
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        add_to_alias(
            settings.db_path,
            alias_name=name,
            offering_canvas_id=offering_id,
        )
        cli_success(f"Offering {offering_id} added to alias '{name}'.")
    except (AliasNotFoundError, OfferingAlreadyInAliasError, AnnotationError) as e:
        cli_error(str(e))


@alias_app.command("remove")
def alias_remove(
    name: Annotated[
        str,
        typer.Argument(help="Name of the alias."),
    ],
    offering_id: Annotated[
        int,
        typer.Argument(help="Canvas course ID to remove from the alias."),
    ],
) -> None:
    """Remove an offering from an alias.

    Examples:
        cl annotate alias remove "BET 3510" 12345
    """
    _ensure_db_exists()
    settings = load_settings()

    try:
        remove_from_alias(
            settings.db_path,
            alias_name=name,
            offering_canvas_id=offering_id,
        )
        cli_success(f"Offering {offering_id} removed from alias '{name}'.")
    except (AliasNotFoundError, OfferingNotInAliasError) as e:
        cli_error(str(e))


@alias_app.command("delete")
def alias_delete_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the alias to delete."),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-y",
            help="Skip confirmation prompt.",
        ),
    ] = False,
) -> None:
    """Delete an alias and all its associations.

    This removes the alias definition. The underlying offerings are not affected.

    Examples:
        cl annotate alias delete "BET 3510"
        cl annotate alias delete "Old Course" --force
    """
    _ensure_db_exists()
    settings = load_settings()

    # Confirm deletion unless --force
    if not force:
        confirm = typer.confirm(f"Delete alias '{name}' and all its associations?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit()

    try:
        delete_alias(settings.db_path, name)
        cli_success(f"Alias '{name}' deleted.")
    except AliasNotFoundError as e:
        cli_error(str(e))


@alias_app.command("list")
def alias_list(
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (table, json, csv).",
        ),
    ] = "table",
) -> None:
    """List all course aliases.

    Examples:
        cl annotate alias list
        cl annotate alias list --format json
    """
    _ensure_db_exists()
    settings = load_settings()

    aliases = list_aliases(settings.db_path)

    if not aliases:
        typer.echo("No aliases found. Use 'cl annotate alias create' to create one.")
        return

    if fmt == "table":
        typer.echo(f"{'Name':<25} {'Offerings':<10} {'Description':<40}")
        typer.echo("-" * 77)
        for alias in aliases:
            name = alias["name"][:24]
            count = alias["offering_count"]
            desc = (alias.get("description") or "")[:39]
            typer.echo(f"{name:<25} {count:<10} {desc:<40}")
    else:
        format_output(aliases, fmt=fmt)


@alias_app.command("show")
def alias_show(
    name: Annotated[
        str,
        typer.Argument(help="Name of the alias to show."),
    ],
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (table, json, csv).",
        ),
    ] = "table",
) -> None:
    """Show details of a specific alias including its offerings.

    Examples:
        cl annotate alias show "BET 3510"
        cl annotate alias show "Intro Programming" --format json
    """
    _ensure_db_exists()
    settings = load_settings()

    from cl.annotations.manager import get_alias
    from cl.ledger.queries import get_offering_by_canvas_id

    alias = get_alias(settings.db_path, name)
    if alias is None:
        cli_error(f"Alias '{name}' not found.")

    try:
        offering_ids = get_alias_offerings(settings.db_path, name)
    except AliasNotFoundError as e:
        cli_error(str(e))

    # Get offering details for each ID
    offerings = []
    for canvas_id in offering_ids:
        offering = get_offering_by_canvas_id(settings.db_path, canvas_id)
        if offering:
            offerings.append(offering.to_dict())
        else:
            offerings.append({"canvas_course_id": canvas_id, "name": "(not in ledger)"})

    if fmt == "json":
        data = alias.to_dict()
        data["offerings"] = offerings
        format_output(data, fmt="json")
    elif fmt == "csv":
        # Flatten for CSV
        rows = []
        for off in offerings:
            rows.append(
                {
                    "alias_name": name,
                    "canvas_course_id": off.get("canvas_course_id"),
                    "offering_name": off.get("name"),
                    "offering_code": off.get("code"),
                }
            )
        format_output(rows, fmt="csv")
    else:
        # Table output
        typer.echo(f"Alias: {alias.name}")
        if alias.description:
            typer.echo(f"Description: {alias.description}")
        typer.echo(f"Created: {alias.created_at.isoformat() if alias.created_at else '(unknown)'}")
        typer.echo("")

        if not offerings:
            typer.echo("No offerings in this alias.")
        else:
            typer.secho(f"Offerings ({len(offerings)}):", bold=True)
            for off in offerings:
                name_display = off.get("name", "(unknown)")
                code = off.get("code", "")
                off_canvas_id = off.get("canvas_course_id")
                if code:
                    typer.echo(f"  - [{code}] {name_display} (ID: {off_canvas_id})")
                else:
                    typer.echo(f"  - {name_display} (ID: {off_canvas_id})")
