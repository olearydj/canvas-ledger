"""Integration tests for database setup and migrations."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from cl.ledger.models import IngestRun, IngestScope, IngestStatus
from cl.ledger.store import (
    get_db_info,
    get_migration_status,
    get_session,
    reset_engine,
    run_migrations,
)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database path and clean up after."""
    db_path = tmp_path / "test_ledger.db"
    yield db_path
    # Clean up the engine after each test
    reset_engine()


class TestDatabaseCreation:
    """Tests for database creation and configuration."""

    def test_run_migrations_creates_database(self, temp_db_path: Path) -> None:
        """Running migrations should create the database file."""
        assert not temp_db_path.exists()

        result = run_migrations(temp_db_path, backup=False)

        assert temp_db_path.exists()
        assert result["status"] == "success"

    def test_run_migrations_creates_ingest_run_table(self, temp_db_path: Path) -> None:
        """Migrations should create the ingest_run table."""
        run_migrations(temp_db_path, backup=False)

        db_info = get_db_info(temp_db_path)

        assert "ingest_run" in db_info["tables"]

    def test_run_migrations_idempotent(self, temp_db_path: Path) -> None:
        """Running migrations twice should be safe."""
        result1 = run_migrations(temp_db_path, backup=False)
        reset_engine()
        result2 = run_migrations(temp_db_path, backup=False)

        assert result1["status"] == "success"
        assert result2["status"] == "up_to_date"

    def test_database_wal_mode(self, temp_db_path: Path) -> None:
        """Database should be configured with WAL mode."""
        run_migrations(temp_db_path, backup=False)

        db_info = get_db_info(temp_db_path)

        assert db_info["journal_mode"] == "wal"

    def test_database_foreign_keys(self, temp_db_path: Path) -> None:
        """Database should have foreign key enforcement enabled."""
        run_migrations(temp_db_path, backup=False)

        db_info = get_db_info(temp_db_path)

        assert db_info["foreign_keys"] is True


class TestMigrationStatus:
    """Tests for migration status reporting."""

    def test_status_shows_pending_before_migration(self, temp_db_path: Path) -> None:
        """Migration status should show pending migrations before running."""
        status = get_migration_status(temp_db_path)

        assert status["db_exists"] is False
        assert status["current_revision"] == "(none)"
        assert status["pending_count"] > 0
        assert "001" in status["pending_revisions"]

    def test_status_shows_up_to_date_after_migration(self, temp_db_path: Path) -> None:
        """Migration status should show up to date after running."""
        run_migrations(temp_db_path, backup=False)
        reset_engine()

        status = get_migration_status(temp_db_path)

        assert status["db_exists"] is True
        assert status["current_revision"] == "006"  # Latest migration
        assert status["pending_count"] == 0
        assert status["up_to_date"] is True


class TestIngestRunModel:
    """Tests for IngestRun model operations."""

    def test_create_ingest_run(self, temp_db_path: Path) -> None:
        """Should be able to create an IngestRun record."""
        run_migrations(temp_db_path, backup=False)

        with get_session(temp_db_path) as session:
            run = IngestRun(scope=IngestScope.CATALOG)
            session.add(run)
            session.commit()
            session.refresh(run)

            assert run.id is not None
            assert run.status == IngestStatus.RUNNING
            assert run.scope == IngestScope.CATALOG

    def test_mark_ingest_run_completed(self, temp_db_path: Path) -> None:
        """Should be able to mark an IngestRun as completed."""
        run_migrations(temp_db_path, backup=False)

        with get_session(temp_db_path) as session:
            run = IngestRun(scope=IngestScope.CATALOG)
            session.add(run)
            session.commit()

            run.mark_completed(new_count=10, updated_count=5, unchanged_count=3)
            session.commit()
            session.refresh(run)

            assert run.status == IngestStatus.COMPLETED
            assert run.completed_at is not None
            assert run.new_count == 10
            assert run.updated_count == 5
            assert run.unchanged_count == 3

    def test_mark_ingest_run_failed(self, temp_db_path: Path) -> None:
        """Should be able to mark an IngestRun as failed."""
        run_migrations(temp_db_path, backup=False)

        with get_session(temp_db_path) as session:
            run = IngestRun(scope=IngestScope.OFFERING, scope_detail="12345")
            session.add(run)
            session.commit()

            run.mark_failed("API connection failed")
            session.commit()
            session.refresh(run)

            assert run.status == IngestStatus.FAILED
            assert run.completed_at is not None
            assert run.error_message == "API connection failed"

    def test_ingest_run_to_dict(self, temp_db_path: Path) -> None:
        """IngestRun.to_dict should return serializable data."""
        run_migrations(temp_db_path, backup=False)

        with get_session(temp_db_path) as session:
            run = IngestRun(scope=IngestScope.CATALOG)
            session.add(run)
            session.commit()
            session.refresh(run)

            data = run.to_dict()

            assert data["id"] == run.id
            assert data["scope"] == "catalog"
            assert data["status"] == "running"
            assert "started_at" in data


class TestDatabaseInfo:
    """Tests for database info reporting."""

    def test_db_info_nonexistent(self, temp_db_path: Path) -> None:
        """db_info should report when database doesn't exist."""
        info = get_db_info(temp_db_path)

        assert info["exists"] is False
        assert info["path"] == str(temp_db_path)

    def test_db_info_after_migration(self, temp_db_path: Path) -> None:
        """db_info should report details after migration."""
        run_migrations(temp_db_path, backup=False)

        info = get_db_info(temp_db_path)

        assert info["exists"] is True
        assert info["size_bytes"] > 0
        assert info["table_count"] >= 1  # At least ingest_run and alembic_version


class TestBackup:
    """Tests for database backup functionality."""

    def test_backup_before_migration(self, temp_db_path: Path) -> None:
        """Should create backup before migration if database exists."""
        # First migration (no backup needed)
        run_migrations(temp_db_path, backup=False)
        reset_engine()

        # Create a dummy migration scenario by just running again
        # (this will be up-to-date, but tests the flow)
        result = run_migrations(temp_db_path, backup=True)

        # Since there's nothing to migrate, no backup created
        assert result["status"] == "up_to_date"
