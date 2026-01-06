"""Unit tests for grade queries (Phase 5).

Tests the performance summary queries that surface Canvas-reported grades.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import select

from cl.ledger.models import Enrollment, Offering, Person, Section, Term
from cl.ledger.queries import get_person_grades
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path and run migrations."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    reset_engine()
    return db_path


@pytest.fixture
def seeded_db_with_grades(temp_db_path: Path) -> Path:
    """Create a database with person, offerings, and enrollments with grade data."""
    with get_session(temp_db_path) as session:
        # Add terms
        term_fall = Term(
            canvas_term_id=1001,
            name="Fall 2025",
            start_date=datetime(2025, 8, 15, tzinfo=UTC),
            end_date=datetime(2025, 12, 15, tzinfo=UTC),
        )
        term_spring = Term(
            canvas_term_id=1002,
            name="Spring 2025",
            start_date=datetime(2025, 1, 15, tzinfo=UTC),
            end_date=datetime(2025, 5, 15, tzinfo=UTC),
        )
        session.add(term_fall)
        session.add(term_spring)
        session.flush()

        # Add offerings
        offering1 = Offering(
            canvas_course_id=12345,
            name="Introduction to Testing",
            code="TEST101",
            term_id=term_fall.id,
            workflow_state="available",
        )
        offering2 = Offering(
            canvas_course_id=12346,
            name="Advanced Testing",
            code="TEST201",
            term_id=term_spring.id,
            workflow_state="available",
        )
        offering3 = Offering(
            canvas_course_id=12347,
            name="Testing Workshop",
            code="TEST110",
            term_id=term_fall.id,
            workflow_state="completed",
        )
        session.add(offering1)
        session.add(offering2)
        session.add(offering3)
        session.flush()

        # Add sections
        section1 = Section(
            canvas_section_id=100,
            offering_id=offering1.id,
            name="Section A",
        )
        section2 = Section(
            canvas_section_id=101,
            offering_id=offering2.id,
            name="Section B",
        )
        session.add(section1)
        session.add(section2)
        session.flush()

        # Add persons
        student = Person(
            canvas_user_id=5001,
            name="Test Student",
            sortable_name="Student, Test",
            sis_user_id="S001",
        )
        teacher = Person(
            canvas_user_id=5002,
            name="Prof. Teacher",
            sortable_name="Teacher, Prof.",
            sis_user_id="T001",
        )
        session.add(student)
        session.add(teacher)
        session.flush()

        # Add enrollments for student with grades
        # Student enrollment 1: has both current and final grades
        enrollment1 = Enrollment(
            canvas_enrollment_id=1001,
            offering_id=offering1.id,
            section_id=section1.id,
            person_id=student.id,
            role="StudentEnrollment",
            enrollment_state="active",
            current_grade="A",
            current_score=95.5,
            final_grade=None,
            final_score=None,
        )
        # Student enrollment 2: has final grades
        enrollment2 = Enrollment(
            canvas_enrollment_id=1002,
            offering_id=offering2.id,
            section_id=section2.id,
            person_id=student.id,
            role="StudentEnrollment",
            enrollment_state="completed",
            current_grade="A-",
            current_score=92.0,
            final_grade="A",
            final_score=93.5,
        )
        # Student enrollment 3: no grade data
        enrollment3 = Enrollment(
            canvas_enrollment_id=1003,
            offering_id=offering3.id,
            section_id=None,
            person_id=student.id,
            role="StudentEnrollment",
            enrollment_state="active",
            current_grade=None,
            current_score=None,
            final_grade=None,
            final_score=None,
        )
        # Teacher enrollment: not a student, should not appear in grades
        enrollment_teacher = Enrollment(
            canvas_enrollment_id=2001,
            offering_id=offering1.id,
            section_id=section1.id,
            person_id=teacher.id,
            role="TeacherEnrollment",
            enrollment_state="active",
            current_grade=None,
            current_score=None,
            final_grade=None,
            final_score=None,
        )
        session.add(enrollment1)
        session.add(enrollment2)
        session.add(enrollment3)
        session.add(enrollment_teacher)
        session.commit()

    reset_engine()
    return temp_db_path


class TestGetPersonGrades:
    """Tests for get_person_grades function."""

    def test_returns_none_for_unknown_person(self, temp_db_path: Path) -> None:
        """Should return None if person not found."""
        result = get_person_grades(temp_db_path, canvas_user_id=99999)
        assert result is None

    def test_returns_grades_for_student_enrollments_only(self, seeded_db_with_grades: Path) -> None:
        """Should only return grades for student enrollments."""
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5001)

        assert result is not None
        assert result.canvas_user_id == 5001
        assert result.person_name == "Test Student"
        assert len(result.grades) == 3  # Three student enrollments

    def test_excludes_non_student_roles(self, seeded_db_with_grades: Path) -> None:
        """Should exclude enrollments where person is not a student."""
        # Teacher has no student enrollments
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5002)

        assert result is not None
        assert result.canvas_user_id == 5002
        assert result.person_name == "Prof. Teacher"
        assert len(result.grades) == 0  # No student enrollments

    def test_includes_grade_fields(self, seeded_db_with_grades: Path) -> None:
        """Should include all grade fields."""
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5001)

        assert result is not None

        # Find the completed enrollment (has final grades)
        completed_enrollment = next(
            (g for g in result.grades if g.enrollment_state == "completed"), None
        )
        assert completed_enrollment is not None
        assert completed_enrollment.current_grade == "A-"
        assert completed_enrollment.current_score == 92.0
        assert completed_enrollment.final_grade == "A"
        assert completed_enrollment.final_score == 93.5

    def test_handles_null_grades(self, seeded_db_with_grades: Path) -> None:
        """Should handle null grades gracefully."""
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5001)

        assert result is not None

        # Find the enrollment without grades
        no_grade_enrollment = next(
            (g for g in result.grades if g.offering_name == "Testing Workshop"), None
        )
        assert no_grade_enrollment is not None
        assert no_grade_enrollment.current_grade is None
        assert no_grade_enrollment.current_score is None
        assert no_grade_enrollment.final_grade is None
        assert no_grade_enrollment.final_score is None

    def test_sorts_by_term_date_descending(self, seeded_db_with_grades: Path) -> None:
        """Should sort grades by term start date, most recent first."""
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5001)

        assert result is not None
        assert len(result.grades) == 3

        # Fall 2025 (Aug) should be before Spring 2025 (Jan)
        term_names = [g.term_name for g in result.grades]
        fall_idx = next(i for i, t in enumerate(term_names) if t == "Fall 2025")
        spring_idx = next(i for i, t in enumerate(term_names) if t == "Spring 2025")
        assert fall_idx < spring_idx  # Fall 2025 is more recent

    def test_to_dict_conversion(self, seeded_db_with_grades: Path) -> None:
        """Should convert to dictionary correctly."""
        result = get_person_grades(seeded_db_with_grades, canvas_user_id=5001)

        assert result is not None
        data = result.to_dict()

        assert data["canvas_user_id"] == 5001
        assert data["person_name"] == "Test Student"
        assert data["sortable_name"] == "Student, Test"
        assert data["total_enrollments"] == 3
        assert len(data["grades"]) == 3

        # Check grade entry structure
        grade_entry = data["grades"][0]
        assert "canvas_course_id" in grade_entry
        assert "offering_name" in grade_entry
        assert "current_grade" in grade_entry
        assert "current_score" in grade_entry
        assert "final_grade" in grade_entry
        assert "final_score" in grade_entry
        assert "enrollment_state" in grade_entry


class TestGradeDriftTracking:
    """Tests for grade drift tracking (T079 verification)."""

    def test_grade_change_creates_change_log(self, temp_db_path: Path) -> None:
        """Grade changes during ingestion should be recorded in change_log.

        Note: This is verified by the existing drift detection tests,
        but we include a specific grade-focused test here for clarity.
        """
        from unittest.mock import MagicMock

        from cl.canvas.client import CourseEnrollmentData, SectionData
        from cl.ledger.ingest import ingest_offering
        from cl.ledger.models import ChangeLog, EntityType

        # Setup: Create offering
        with get_session(temp_db_path) as session:
            term = Term(canvas_term_id=1001, name="Fall 2025")
            session.add(term)
            session.flush()

            offering = Offering(
                canvas_course_id=12345,
                name="Test Course",
                code="TEST101",
                term_id=term.id,
                workflow_state="available",
            )
            session.add(offering)
            session.commit()

        reset_engine()

        # First ingestion
        mock_client = MagicMock()
        mock_client.list_sections.return_value = [
            SectionData(
                canvas_section_id=100,
                course_id=12345,
                name="Section A",
                sis_section_id=None,
            )
        ]
        mock_client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=1001,
                course_id=12345,
                course_section_id=100,
                user_id=5001,
                role="StudentEnrollment",
                enrollment_state="active",
                user_name="Test Student",
                user_sortable_name="Student, Test",
                user_sis_id="S001",
                user_login_id="student@example.com",
                current_grade="B",
                current_score=85.0,
                final_grade=None,
                final_score=None,
            )
        ]

        ingest_offering(mock_client, temp_db_path, canvas_course_id=12345)

        # Second ingestion with grade change
        mock_client.list_enrollments.return_value = [
            CourseEnrollmentData(
                canvas_enrollment_id=1001,
                course_id=12345,
                course_section_id=100,
                user_id=5001,
                role="StudentEnrollment",
                enrollment_state="active",
                user_name="Test Student",
                user_sortable_name="Student, Test",
                user_sis_id="S001",
                user_login_id="student@example.com",
                current_grade="A",  # Grade improved
                current_score=95.0,  # Score improved
                final_grade=None,
                final_score=None,
            )
        ]

        result = ingest_offering(mock_client, temp_db_path, canvas_course_id=12345)

        # Should have recorded grade changes
        assert result.updated_count >= 1

        # Check change log
        with get_session(temp_db_path) as session:
            grade_changes = list(
                session.exec(
                    select(ChangeLog)
                    .where(ChangeLog.entity_type == EntityType.ENROLLMENT)
                    .where(ChangeLog.entity_canvas_id == 1001)
                    .where(ChangeLog.field_name.in_(["current_grade", "current_score"]))
                ).all()
            )

            assert len(grade_changes) == 2  # current_grade and current_score

            grade_change = next(c for c in grade_changes if c.field_name == "current_grade")
            assert grade_change.old_value == "B"
            assert grade_change.new_value == "A"

            score_change = next(c for c in grade_changes if c.field_name == "current_score")
            assert score_change.old_value == "85.0"
            assert score_change.new_value == "95.0"
