"""Database command group for canvas-ledger CLI.

Commands:
- cl db migrate: Run pending migrations
- cl db status: Show migration status and database info
"""

from __future__ import annotations

import typer

from cl.config.settings import get_default_config_path, get_default_db_path, load_settings
from cl.ledger.store import get_db_info, get_migration_status, run_migrations

app = typer.Typer(
    name="db",
    help="""Database operations for canvas-ledger.

The ledger is stored in a local SQLite database (~/.local/share/cl/ledger.db
by default). Run 'cl db migrate' after first install and after updates to
ensure the schema is current.
""",
    no_args_is_help=True,
)


def _get_db_path() -> str:
    """Get the database path from config or default."""
    config_path = get_default_config_path()

    if config_path.exists():
        settings = load_settings(config_path)
        return str(settings.db_path)

    return str(get_default_db_path())


@app.command("migrate")
def db_migrate(
    no_backup: bool = typer.Option(
        False,
        "--no-backup",
        help="Skip automatic backup before migration.",
    ),
) -> None:
    """Run pending database migrations.

    Applies any schema changes needed for the current version of canvas-ledger.
    A backup is created automatically before migration (unless --no-backup).
    \b
    When to run:
      • After first install (creates the database)
      • After updating canvas-ledger
      • If 'cl db status' shows pending migrations
    """
    db_path = _get_db_path()

    typer.echo(f"Database: {db_path}")

    # Run migrations
    result = run_migrations(db_path, backup=not no_backup)

    if result["status"] == "up_to_date":
        typer.secho("Database is up to date.", fg=typer.colors.GREEN)
        return

    if result["status"] == "success":
        applied = result.get("applied", [])
        typer.secho(f"Applied {len(applied)} migration(s):", fg=typer.colors.GREEN)
        for rev in applied:
            typer.echo(f"  - {rev}")

        if "backup_path" in result:
            typer.echo(f"Backup created: {result['backup_path']}")

        typer.echo(f"Current revision: {result.get('current_revision', 'unknown')}")
    else:
        typer.secho("Migration failed!", fg=typer.colors.RED, err=True)
        if "error" in result:
            typer.echo(f"Error: {result['error']}", err=True)
        if "backup_available" in result:
            typer.echo(f"Backup available at: {result['backup_available']}")
        raise typer.Exit(1)


@app.command("status")
def db_status() -> None:
    """Show database and migration status.

    Displays information about the database file and migration state.
    """
    db_path = _get_db_path()

    # Get database info
    db_info = get_db_info(db_path)

    typer.echo("Database Information:")
    typer.echo(f"  Path: {db_info['path']}")
    typer.echo(f"  Exists: {db_info['exists']}")

    if db_info["exists"]:
        size_bytes = db_info.get("size_bytes", 0)
        size_kb = int(size_bytes) / 1024 if isinstance(size_bytes, int) else 0
        typer.echo(f"  Size: {size_kb:.1f} KB")
        typer.echo(f"  Tables: {db_info.get('tables', '(none)')}")
        typer.echo(f"  Journal mode: {db_info.get('journal_mode', 'unknown')}")
        typer.echo(f"  Foreign keys: {db_info.get('foreign_keys', 'unknown')}")

    typer.echo()

    # Get migration status
    migration_status = get_migration_status(db_path)

    typer.echo("Migration Status:")
    typer.echo(f"  Head revision: {migration_status['head_revision']}")
    typer.echo(f"  Current revision: {migration_status['current_revision']}")

    pending_raw = migration_status.get("pending_revisions", [])
    pending: list[str] = pending_raw if isinstance(pending_raw, list) else []
    if pending:
        typer.secho(f"  Pending migrations: {len(pending)}", fg=typer.colors.YELLOW)
        for rev in pending:
            typer.echo(f"    - {rev}")
    else:
        typer.secho("  Status: Up to date", fg=typer.colors.GREEN)
