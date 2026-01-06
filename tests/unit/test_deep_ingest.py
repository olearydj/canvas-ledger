"""Unit tests for deep ingestion (ingest_offering).

Tests the ingestion of sections, enrollments, and people for a specific offering.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from cl.canvas.client import CourseEnrollmentData, SectionData
from cl.ledger.ingest import ingest_offering
from cl.ledger.models import Enrollment, Offering, Person, Section, Term
from cl.ledger.store import get_session, reset_engine, run_migrations

# Fixed course ID for all tests - each test gets its own temp db
COURSE_ID = 12345


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path and run migrations."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    reset_engine()
    return db_path


@pytest.fixture
def seeded_db(temp_db_path: Path) -> Path:
    """Create a database with a pre-seeded offering and term."""
    with get_session(temp_db_path) as session:
        # Add a term
        term = Term(
            canvas_term_id=1001,
            name="Fall 2025",
            start_date=None,
            end_date=None,
        )
        session.add(term)
        session.flush()

        # Add an offering
        offering = Offering(
            canvas_course_id=COURSE_ID,
            name="Test Course",
            code="TEST101",
            term_id=term.id,
            workflow_state="available",
        )
        session.add(offering)
        session.commit()

    reset_engine()  # Reset again after seeding
    return temp_db_path


def mock_sections(course_id: int = COURSE_ID) -> list[SectionData]:
    """Create mock section data."""
    return [
        SectionData(
            canvas_section_id=100,
            course_id=course_id,
            name="Section A",
            sis_section_id="SEC-A",
        ),
        SectionData(
            canvas_section_id=101,
            course_id=course_id,
            name="Section B",
            sis_section_id="SEC-B",
        ),
    ]


def mock_enrollments(course_id: int = COURSE_ID) -> list[CourseEnrollmentData]:
    """Create mock enrollment data."""
    return [
        CourseEnrollmentData(
            canvas_enrollment_id=1000,
            course_id=course_id,
            course_section_id=100,
            user_id=5001,
            role="TeacherEnrollment",
            enrollment_state="active",
            user_name="Dr. Teacher",
            user_sortable_name="Teacher, Dr.",
            user_sis_id="T001",
            user_login_id="teacher@example.com",
            current_grade=None,
            current_score=None,
            final_grade=None,
            final_score=None,
        ),
        CourseEnrollmentData(
            canvas_enrollment_id=1001,
            course_id=course_id,
            course_section_id=100,
            user_id=5002,
            role="StudentEnrollment",
            enrollment_state="active",
            user_name="Student One",
            user_sortable_name="One, Student",
            user_sis_id="S001",
            user_login_id="student1@example.com",
            current_grade="A",
            current_score=95.0,
            final_grade=None,
            final_score=None,
        ),
        CourseEnrollmentData(
            canvas_enrollment_id=1002,
            course_id=course_id,
            course_section_id=101,
            user_id=5003,
            role="StudentEnrollment",
            enrollment_state="active",
            user_name="Student Two",
            user_sortable_name="Two, Student",
            user_sis_id="S002",
            user_login_id="student2@example.com",
            current_grade="B",
            current_score=85.0,
            final_grade=None,
            final_score=None,
        ),
    ]


class TestIngestOffering:
    """Tests for ingest_offering function."""

    def test_ingest_offering_not_found_locally(self, temp_db_path: Path) -> None:
        """Should return error if offering not found locally."""
        mock_client = MagicMock()

        result = ingest_offering(mock_client, temp_db_path, canvas_course_id=99999)

        assert result.error is not None
        assert "not found locally" in result.error
        assert result.run_id == 0

    def test_ingest_offering_creates_sections(self, seeded_db: Path) -> None:
        """Should create section records for the offering."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = []

        result = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        assert result.error is None
        assert result.new_count == 2  # Two sections

        with get_session(seeded_db) as session:
            sections = list(session.exec(select(Section)).all())
            assert len(sections) == 2
            assert {s.name for s in sections} == {"Section A", "Section B"}

    def test_ingest_offering_creates_people(self, seeded_db: Path) -> None:
        """Should create person records for enrolled users."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        result = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        assert result.error is None

        with get_session(seeded_db) as session:
            people = list(session.exec(select(Person)).all())
            assert len(people) == 3
            assert {p.name for p in people} == {"Dr. Teacher", "Student One", "Student Two"}

    def test_ingest_offering_creates_enrollments(self, seeded_db: Path) -> None:
        """Should create enrollment records with correct attributes."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        result = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        assert result.error is None

        with get_session(seeded_db) as session:
            enrollments = list(session.exec(select(Enrollment)).all())
            assert len(enrollments) == 3

            # Check teacher enrollment
            teacher_enroll = next(e for e in enrollments if e.canvas_enrollment_id == 1000)
            assert teacher_enroll.role == "TeacherEnrollment"
            assert teacher_enroll.enrollment_state == "active"

            # Check student with grade
            student_enroll = next(e for e in enrollments if e.canvas_enrollment_id == 1001)
            assert student_enroll.role == "StudentEnrollment"
            assert student_enroll.current_grade == "A"
            assert student_enroll.current_score == 95.0

    def test_ingest_offering_links_enrollments_to_sections(self, seeded_db: Path) -> None:
        """Should correctly link enrollments to their sections."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        with get_session(seeded_db) as session:
            # Get section A
            section_a = session.exec(select(Section).where(Section.name == "Section A")).first()
            assert section_a is not None

            # Check enrollments in Section A
            enrollments_a = list(
                session.exec(select(Enrollment).where(Enrollment.section_id == section_a.id)).all()
            )
            assert len(enrollments_a) == 2  # Teacher and Student One


class TestDeepIngestIdempotency:
    """Tests for idempotency of deep ingestion."""

    def test_duplicate_ingestion_no_duplicates(self, seeded_db: Path) -> None:
        """Running ingestion twice should not create duplicates."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        # First ingestion
        result1 = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)
        assert result1.error is None

        # Second ingestion
        result2 = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)
        assert result2.error is None

        # Should have no new records in second run
        assert result2.new_count == 0
        assert result2.unchanged_count >= 5  # 2 sections + 3 enrollments

        # Check database has no duplicates
        with get_session(seeded_db) as session:
            sections = list(session.exec(select(Section)).all())
            people = list(session.exec(select(Person)).all())
            enrollments = list(session.exec(select(Enrollment)).all())

            assert len(sections) == 2
            assert len(people) == 3
            assert len(enrollments) == 3

    def test_updated_enrollment_state_triggers_update(self, seeded_db: Path) -> None:
        """Changing enrollment state should trigger an update."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        # First ingestion
        result1 = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)
        assert result1.error is None

        # Modify enrollment state
        updated_enrollments = mock_enrollments()
        updated_enrollments[1] = CourseEnrollmentData(
            canvas_enrollment_id=1001,
            course_id=COURSE_ID,
            course_section_id=100,
            user_id=5002,
            role="StudentEnrollment",
            enrollment_state="completed",  # Changed from "active"
            user_name="Student One",
            user_sortable_name="One, Student",
            user_sis_id="S001",
            user_login_id="student1@example.com",
            current_grade="A",
            current_score=95.0,
            final_grade="A",
            final_score=95.0,
        )
        mock_client.list_enrollments.return_value = updated_enrollments

        # Second ingestion
        result2 = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)
        assert result2.error is None
        assert result2.updated_count >= 1  # At least the enrollment was updated

        # Check enrollment state was updated
        with get_session(seeded_db) as session:
            enrollment = session.exec(
                select(Enrollment).where(Enrollment.canvas_enrollment_id == 1001)
            ).first()
            assert enrollment is not None
            assert enrollment.enrollment_state == "completed"
            assert enrollment.final_grade == "A"

    def test_drift_detection_person_name(self, seeded_db: Path) -> None:
        """Should detect drift when person name changes."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()
        mock_client.list_enrollments.return_value = mock_enrollments()

        # First ingestion
        ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        # Update person name
        updated_enrollments = mock_enrollments()
        updated_enrollments[0] = CourseEnrollmentData(
            canvas_enrollment_id=1000,
            course_id=COURSE_ID,
            course_section_id=100,
            user_id=5001,
            role="TeacherEnrollment",
            enrollment_state="active",
            user_name="Prof. Teacher",  # Changed from "Dr. Teacher"
            user_sortable_name="Teacher, Prof.",
            user_sis_id="T001",
            user_login_id="teacher@example.com",
            current_grade=None,
            current_score=None,
            final_grade=None,
            final_score=None,
        )
        mock_client.list_enrollments.return_value = updated_enrollments

        # Second ingestion
        result2 = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)
        assert result2.error is None
        assert len(result2.drift_detected) >= 1
        assert any("Person" in d and "name" in d for d in result2.drift_detected)


class TestIngestRunTracking:
    """Tests for ingest run metadata tracking."""

    def test_creates_ingest_run_record(self, seeded_db: Path) -> None:
        """Should create an ingest run record with offering scope."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = []
        mock_client.list_enrollments.return_value = []

        result = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        assert result.error is None
        assert result.run_id > 0

    def test_ingest_run_counts_are_accurate(self, seeded_db: Path) -> None:
        """Ingest run should have accurate counts."""
        mock_client = MagicMock()
        mock_client.list_sections.return_value = mock_sections()  # 2 sections
        mock_client.list_enrollments.return_value = mock_enrollments()  # 3 enrollments

        result = ingest_offering(mock_client, seeded_db, canvas_course_id=COURSE_ID)

        assert result.error is None
        # 2 sections + 3 people + 3 enrollments = 8 new
        assert result.new_count == 8
        assert result.total_count == 8
