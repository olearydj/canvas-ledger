"""Integration tests for Phase 4 drift tracking functionality.

Tests the change_log table, drift detection during ingestion,
and drift query functions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cl.canvas.client import (
    CanvasClient,
    CourseData,
    CourseEnrollmentData,
    EnrollmentData,
    SectionData,
)
from cl.ledger.ingest import ingest_catalog, ingest_offering
from cl.ledger.models import ChangeLog, EntityType
from cl.ledger.queries import get_changes_by_ingest_run, get_offering_drift, get_person_drift
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temp database with migrations run."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


class TestChangeLogRecording:
    """Tests for change_log table recording during ingestion."""

    def test_offering_name_change_recorded(self, temp_db_path: Path) -> None:
        """Changing offering name should create a change_log entry."""
        client = MagicMock(spec=CanvasClient)

        # First ingest with original name
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=101,
                name="Original Name",
                code="CODE101",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=101,
                    )
                ],
            )
        ]

        result1 = ingest_catalog(client, temp_db_path)
        assert result1.new_count > 0

        # Second ingest with changed name
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=101,
                name="Changed Name",  # Changed!
                code="CODE101",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=101,
                    )
                ],
            )
        ]

        result2 = ingest_catalog(client, temp_db_path)
        assert result2.updated_count > 0

        # Check change_log has the name change
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            changes = list(
                session.exec(
                    select(ChangeLog)
                    .where(ChangeLog.entity_type == EntityType.OFFERING)
                    .where(ChangeLog.field_name == "name")
                ).all()
            )

            assert len(changes) == 1
            assert changes[0].old_value == "Original Name"
            assert changes[0].new_value == "Changed Name"
            assert changes[0].entity_canvas_id == 101

    def test_enrollment_state_change_recorded(self, temp_db_path: Path) -> None:
        """Changing enrollment state should create a change_log entry."""
        client = MagicMock(spec=CanvasClient)

        # First ingest with active enrollment
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=102,
                name="Course 102",
                code="C102",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1002,
                        role="StudentEnrollment",
                        enrollment_state="active",
                        course_id=102,
                    )
                ],
            )
        ]

        ingest_catalog(client, temp_db_path)

        # Second ingest with completed enrollment
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=102,
                name="Course 102",
                code="C102",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1002,
                        role="StudentEnrollment",
                        enrollment_state="completed",  # Changed!
                        course_id=102,
                    )
                ],
            )
        ]

        ingest_catalog(client, temp_db_path)

        # Check change_log has the state change
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            changes = list(
                session.exec(
                    select(ChangeLog)
                    .where(ChangeLog.entity_type == EntityType.USER_ENROLLMENT)
                    .where(ChangeLog.field_name == "enrollment_state")
                ).all()
            )

            assert len(changes) == 1
            assert changes[0].old_value == "active"
            assert changes[0].new_value == "completed"

    def test_drift_count_updated_on_ingest_run(self, temp_db_path: Path) -> None:
        """Ingest run should track total drift count."""
        client = MagicMock(spec=CanvasClient)

        # First ingest
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=103,
                name="Course 103",
                code="C103",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1003,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=103,
                    )
                ],
            )
        ]

        ingest_catalog(client, temp_db_path)

        # Second ingest with multiple changes
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=103,
                name="Course 103 Updated",  # Changed!
                code="C103-NEW",  # Changed!
                workflow_state="completed",  # Changed!
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=1003,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=103,
                    )
                ],
            )
        ]

        ingest_catalog(client, temp_db_path)

        # Check ingest run has drift count
        from cl.ledger.ingest import get_last_ingest_run

        run = get_last_ingest_run(temp_db_path)
        assert run is not None
        assert run.drift_count == 3  # name, code, workflow_state


class TestDeepIngestDriftTracking:
    """Tests for drift tracking during deep ingestion."""

    def test_person_name_change_recorded(self, temp_db_path: Path) -> None:
        """Person name change during deep ingest should be recorded."""
        client = MagicMock(spec=CanvasClient)

        # Set up catalog first
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=201,
                name="Course 201",
                code="C201",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=2001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=201,
                    )
                ],
            )
        ]
        ingest_catalog(client, temp_db_path)

        # First deep ingest
        client.list_sections.return_value = [
            SectionData(canvas_section_id=301, course_id=201, name="Section A", sis_section_id=None)
        ]
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=4001,
                course_id=201,
                user_id=5001,
                user_name="John Doe",
                user_sortable_name="Doe, John",
                user_sis_id=None,
                user_login_id=None,
                course_section_id=301,
                role="StudentEnrollment",
                enrollment_state="active",
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 201)

        # Second deep ingest with name change
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=4001,
                course_id=201,
                user_id=5001,
                user_name="John Smith",  # Changed!
                user_sortable_name="Smith, John",  # Changed!
                user_sis_id=None,
                user_login_id=None,
                course_section_id=301,
                role="StudentEnrollment",
                enrollment_state="active",
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 201)

        # Check change_log has person name change
        with get_session(temp_db_path) as session:
            from sqlmodel import select

            changes = list(
                session.exec(
                    select(ChangeLog)
                    .where(ChangeLog.entity_type == EntityType.PERSON)
                    .where(ChangeLog.field_name == "name")
                ).all()
            )

            assert len(changes) == 1
            assert changes[0].old_value == "John Doe"
            assert changes[0].new_value == "John Smith"


class TestDriftQueries:
    """Tests for drift query functions."""

    def test_get_person_drift_returns_changes(self, temp_db_path: Path) -> None:
        """get_person_drift should return all changes for a person."""
        client = MagicMock(spec=CanvasClient)

        # Set up catalog
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=301,
                name="Course 301",
                code="C301",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=3001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=301,
                    )
                ],
            )
        ]
        ingest_catalog(client, temp_db_path)

        # First deep ingest
        client.list_sections.return_value = [
            SectionData(canvas_section_id=401, course_id=301, name="Section", sis_section_id=None)
        ]
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=5001,
                course_id=301,
                user_id=6001,
                user_name="Test Student",
                user_sortable_name="Student, Test",
                user_sis_id=None,
                user_login_id=None,
                course_section_id=401,
                role="StudentEnrollment",
                enrollment_state="active",
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 301)

        # Second deep ingest with changes
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=5001,
                course_id=301,
                user_id=6001,
                user_name="Test Student Updated",  # Changed!
                user_sortable_name="Student, Test",
                user_sis_id=None,
                user_login_id=None,
                course_section_id=401,
                role="StudentEnrollment",
                enrollment_state="completed",  # Changed!
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 301)

        # Query person drift
        drift = get_person_drift(temp_db_path, 6001)

        assert drift is not None
        assert drift.canvas_user_id == 6001
        assert len(drift.changes) >= 2  # name and enrollment_state

    def test_get_offering_drift_returns_all_related_changes(self, temp_db_path: Path) -> None:
        """get_offering_drift should return changes for offering, sections, and enrollments."""
        client = MagicMock(spec=CanvasClient)

        # Set up catalog
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=401,
                name="Course 401",
                code="C401",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=4001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=401,
                    )
                ],
            )
        ]
        ingest_catalog(client, temp_db_path)

        # Deep ingest
        client.list_sections.return_value = [
            SectionData(
                canvas_section_id=501, course_id=401, name="Original Section", sis_section_id=None
            )
        ]
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=6001,
                course_id=401,
                user_id=7001,
                user_name="Student One",
                user_sortable_name=None,
                user_sis_id=None,
                user_login_id=None,
                course_section_id=501,
                role="StudentEnrollment",
                enrollment_state="active",
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 401)

        # Second ingest with changes
        client.list_sections.return_value = [
            SectionData(
                canvas_section_id=501, course_id=401, name="Renamed Section", sis_section_id=None
            )  # Changed!
        ]
        client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=6001,
                course_id=401,
                user_id=7001,
                user_name="Student One",
                user_sortable_name=None,
                user_sis_id=None,
                user_login_id=None,
                course_section_id=501,
                role="StudentEnrollment",
                enrollment_state="completed",  # Changed!
                current_grade=None,
                current_score=None,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(client, temp_db_path, 401)

        # Query offering drift
        drift = get_offering_drift(temp_db_path, 401)

        assert drift is not None
        assert drift.canvas_course_id == 401
        # Should have section name change + enrollment state change
        assert len(drift.changes) >= 2

    def test_get_person_drift_returns_none_for_unknown(self, temp_db_path: Path) -> None:
        """get_person_drift should return None for unknown person."""
        drift = get_person_drift(temp_db_path, 99999)
        assert drift is None

    def test_get_offering_drift_returns_none_for_unknown(self, temp_db_path: Path) -> None:
        """get_offering_drift should return None for unknown offering."""
        drift = get_offering_drift(temp_db_path, 99999)
        assert drift is None


class TestGetChangesByIngestRun:
    """Tests for get_changes_by_ingest_run function."""

    def test_returns_changes_for_run(self, temp_db_path: Path) -> None:
        """Should return all changes for a specific ingest run."""
        client = MagicMock(spec=CanvasClient)

        # First ingest
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=501,
                name="Course 501",
                code="C501",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=5001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=501,
                    )
                ],
            )
        ]

        ingest_catalog(client, temp_db_path)

        # Second ingest with changes
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=501,
                name="Course 501 Updated",  # Changed!
                code="C501",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=5001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=501,
                    )
                ],
            )
        ]

        result2 = ingest_catalog(client, temp_db_path)
        run_id2 = result2.run_id

        # Check changes for run 2 only
        changes = get_changes_by_ingest_run(temp_db_path, run_id2)

        assert len(changes) == 1
        assert changes[0].field_name == "name"
        assert changes[0].old_value == "Course 501"
        assert changes[0].new_value == "Course 501 Updated"

    def test_returns_empty_for_no_changes(self, temp_db_path: Path) -> None:
        """Should return empty list when no changes in run."""
        client = MagicMock(spec=CanvasClient)

        # Single ingest - no changes possible on first run
        client.list_my_courses.return_value = [
            CourseData(
                canvas_course_id=601,
                name="Course 601",
                code="C601",
                workflow_state="available",
                term_id=None,
                enrollments=[
                    EnrollmentData(
                        canvas_enrollment_id=6001,
                        role="TeacherEnrollment",
                        enrollment_state="active",
                        course_id=601,
                    )
                ],
            )
        ]

        result = ingest_catalog(client, temp_db_path)
        changes = get_changes_by_ingest_run(temp_db_path, result.run_id)

        assert changes == []
