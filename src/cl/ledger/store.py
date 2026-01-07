"""Database connection and session management for canvas-ledger.

Provides SQLite configuration with recommended operational defaults:
- WAL mode for better concurrency
- Foreign key enforcement
- Busy timeout for handling locks
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine, event, text
from sqlmodel import Session, SQLModel, create_engine

if TYPE_CHECKING:
    from alembic.config import Config as AlembicConfig
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

# Global engine instance (lazily initialized)
_engine: Engine | None = None


def get_engine(db_path: Path | str, echo: bool = False) -> Engine:
    """Get or create the database engine.

    Args:
        db_path: Path to the SQLite database file.
        echo: If True, log all SQL statements.

    Returns:
        SQLAlchemy Engine configured for SQLite.
    """
    global _engine

    if _engine is not None:
        return _engine

    # Ensure parent directory exists
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create engine with SQLite-specific configuration
    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=echo,
        connect_args={"check_same_thread": False},
    )

    # Configure SQLite operational defaults on each connection
    @event.listens_for(_engine, "connect")
    def set_sqlite_pragma(
        dbapi_connection: DBAPIConnection,
        _connection_record: ConnectionPoolEntry,
    ) -> None:
        """Set SQLite pragmas for WAL mode, foreign keys, and busy timeout."""
        cursor = dbapi_connection.cursor()
        # WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        # Enforce foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # 5 second busy timeout
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return _engine


def reset_engine() -> None:
    """Reset the global engine (for testing)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def get_session(db_path: Path | str) -> Generator[Session]:
    """Context manager for database sessions.

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        SQLModel Session for database operations.
    """
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session


def create_all_tables(db_path: Path | str) -> None:
    """Create all tables defined in SQLModel metadata.

    Note: In production, use Alembic migrations instead.
    This is primarily for testing.

    Args:
        db_path: Path to the SQLite database file.
    """
    engine = get_engine(db_path)
    SQLModel.metadata.create_all(engine)


def backup_database(db_path: Path | str, suffix: str | None = None) -> Path:
    """Create a backup of the database file.

    Args:
        db_path: Path to the SQLite database file.
        suffix: Optional suffix for backup filename. Defaults to timestamp.

    Returns:
        Path to the backup file.

    Raises:
        FileNotFoundError: If the database file doesn't exist.
    """
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    if suffix is None:
        suffix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    backup_path = db_path.with_suffix(f".{suffix}.backup")
    shutil.copy2(db_path, backup_path)

    return backup_path


def get_db_info(db_path: Path | str) -> dict[str, str | int | bool]:
    """Get information about the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with database info (exists, size, tables, etc.).
    """
    db_path = Path(db_path)

    info: dict[str, str | int | bool] = {
        "path": str(db_path),
        "exists": db_path.exists(),
    }

    if not db_path.exists():
        return info

    info["size_bytes"] = db_path.stat().st_size

    # Get table count and names
    engine = get_engine(db_path)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = [row[0] for row in result]
        info["table_count"] = len(tables)
        info["tables"] = ", ".join(tables) if tables else "(none)"

        # Get journal mode
        result = conn.execute(text("PRAGMA journal_mode"))
        journal_mode = result.scalar()
        info["journal_mode"] = str(journal_mode) if journal_mode else "unknown"

        # Get foreign keys status
        result = conn.execute(text("PRAGMA foreign_keys"))
        info["foreign_keys"] = bool(result.scalar())

    return info


# --- Migration functions ---


def get_alembic_config(db_path: Path | str) -> AlembicConfig:
    """Get Alembic configuration for the given database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Alembic Config object.
    """
    from alembic.config import Config as AlembicConfig

    # Find the alembic.ini relative to this package
    import cl

    package_dir = Path(cl.__file__).parent
    alembic_ini = package_dir.parent.parent / "alembic.ini"

    if not alembic_ini.exists():
        # Fall back to current directory
        alembic_ini = Path("alembic.ini")

    config = AlembicConfig(str(alembic_ini))

    # Override the database URL
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    return config


def get_current_revision(db_path: Path | str) -> str | None:
    """Get the current migration revision for the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Current revision string or None if no migrations applied.
    """
    from alembic.runtime.migration import MigrationContext

    db_path = Path(db_path)
    if not db_path.exists():
        return None

    engine = get_engine(db_path)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def get_pending_migrations(db_path: Path | str) -> list[str]:
    """Get list of pending migrations.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        List of pending revision IDs.
    """
    from alembic.script import ScriptDirectory

    config = get_alembic_config(db_path)
    script = ScriptDirectory.from_config(config)

    current = get_current_revision(db_path)

    # Get all revisions from current to head
    pending = []
    for rev in script.iterate_revisions("head", current):
        if rev.revision != current:
            pending.append(rev.revision)

    # Reverse to get chronological order
    pending.reverse()
    return pending


def run_migrations(db_path: Path | str, backup: bool = True) -> dict[str, str | list[str]]:
    """Run all pending migrations.

    Args:
        db_path: Path to the SQLite database file.
        backup: If True, backup database before migrating.

    Returns:
        Dictionary with migration results (current, applied, etc.).
    """
    from alembic import command

    db_path = Path(db_path)
    result: dict[str, str | list[str]] = {
        "db_path": str(db_path),
    }

    # Get current state
    current = get_current_revision(db_path)
    result["previous_revision"] = current or "(none)"

    pending = get_pending_migrations(db_path)
    result["pending"] = pending

    if not pending:
        result["status"] = "up_to_date"
        result["applied"] = []
        return result

    # Backup if database exists
    backup_path: Path | None = None
    if backup and db_path.exists():
        backup_path = backup_database(db_path, suffix="pre_migration")
        result["backup_path"] = str(backup_path)

    # Run migrations
    config = get_alembic_config(db_path)
    try:
        command.upgrade(config, "head")
        result["status"] = "success"
        result["applied"] = pending
        result["current_revision"] = get_current_revision(db_path) or "(none)"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        if backup_path:
            result["backup_available"] = str(backup_path)

    return result


def get_migration_status(db_path: Path | str) -> dict[str, str | int | list[str] | bool]:
    """Get migration status for the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with migration status info.
    """
    from alembic.script import ScriptDirectory

    config = get_alembic_config(db_path)
    script = ScriptDirectory.from_config(config)

    db_path = Path(db_path)

    status: dict[str, str | int | list[str] | bool] = {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
    }

    # Get head revision
    heads = script.get_heads()
    status["head_revision"] = heads[0] if heads else "(none)"

    # Get current revision
    current = get_current_revision(db_path)
    status["current_revision"] = current or "(none)"

    # Get pending migrations
    pending = get_pending_migrations(db_path)
    status["pending_count"] = len(pending)
    status["pending_revisions"] = pending

    status["up_to_date"] = len(pending) == 0

    return status
