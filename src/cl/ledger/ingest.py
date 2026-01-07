"""Ingestion engine for canvas-ledger.

Orchestrates data retrieval from Canvas and persistence to the local ledger.
Supports catalog ingestion (all visible courses) and deep ingestion (per-offering).

All ingestion is:
- Idempotent: Same input produces same ledger state
- Drift-aware: Detects changes from prior observations
- Non-destructive: Never deletes observed data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from cl.canvas.client import (
    CanvasClient,
    CanvasClientError,
    CanvasNotFoundError,
    CourseData,
    CourseEnrollmentData,
    SectionData,
    TermData,
)
from cl.ledger.models import (
    ChangeLog,
    Enrollment,
    EntityType,
    IngestRun,
    IngestScope,
    Offering,
    Person,
    Section,
    Term,
    UserEnrollment,
)
from cl.ledger.store import get_session

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of an ingestion run."""

    run_id: int
    new_count: int
    updated_count: int
    unchanged_count: int
    drift_detected: list[str]  # List of drift descriptions
    error: str | None = None

    @property
    def total_count(self) -> int:
        """Total number of records processed (new + updated + unchanged)."""
        return self.new_count + self.updated_count + self.unchanged_count

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "new_count": self.new_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
            "total_count": self.total_count,
            "drift_detected": self.drift_detected,
            "error": self.error,
        }


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def _record_change(
    session: Session,
    entity_type: EntityType,
    entity_canvas_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    ingest_run_id: int,
    observed_at: datetime,
) -> None:
    """Record a change in the change_log table.

    Converts values to strings for storage. None values are stored as-is.
    """
    change = ChangeLog(
        entity_type=entity_type,
        entity_canvas_id=entity_canvas_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        ingest_run_id=ingest_run_id,
        observed_at=observed_at,
    )
    session.add(change)


def _upsert_term(
    session: Session, term_data: TermData, ingest_run_id: int
) -> tuple[Term, str, int]:
    """Upsert a term record.

    Returns:
        Tuple of (Term, status, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(Term).where(Term.canvas_term_id == term_data.canvas_term_id)
    existing = session.exec(stmt).first()

    now = _utcnow()
    change_count = 0

    if existing is None:
        term = Term(
            canvas_term_id=term_data.canvas_term_id,
            name=term_data.name,
            start_date=term_data.start_date,
            end_date=term_data.end_date,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(term)
        return term, "new", 0

    # Check for drift (changes in data)
    drift = False
    if existing.name != term_data.name:
        logger.info(
            f"Term {term_data.canvas_term_id} name drift: '{existing.name}' -> '{term_data.name}'"
        )
        _record_change(
            session,
            EntityType.TERM,
            term_data.canvas_term_id,
            "name",
            existing.name,
            term_data.name,
            ingest_run_id,
            now,
        )
        existing.name = term_data.name
        drift = True
        change_count += 1

    if existing.start_date != term_data.start_date:
        _record_change(
            session,
            EntityType.TERM,
            term_data.canvas_term_id,
            "start_date",
            existing.start_date,
            term_data.start_date,
            ingest_run_id,
            now,
        )
        existing.start_date = term_data.start_date
        drift = True
        change_count += 1

    if existing.end_date != term_data.end_date:
        _record_change(
            session,
            EntityType.TERM,
            term_data.canvas_term_id,
            "end_date",
            existing.end_date,
            term_data.end_date,
            ingest_run_id,
            now,
        )
        existing.end_date = term_data.end_date
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", change_count

    return existing, "unchanged", 0


def _upsert_offering(
    session: Session,
    course_data: CourseData,
    term_id: int | None,
    ingest_run_id: int,
) -> tuple[Offering, str, list[str], int]:
    """Upsert an offering record.

    Returns:
        Tuple of (Offering, status, drift_list, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(Offering).where(Offering.canvas_course_id == course_data.canvas_course_id)
    existing = session.exec(stmt).first()

    now = _utcnow()
    drift_list: list[str] = []
    change_count = 0

    if existing is None:
        offering = Offering(
            canvas_course_id=course_data.canvas_course_id,
            name=course_data.name,
            code=course_data.code,
            term_id=term_id,
            workflow_state=course_data.workflow_state,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(offering)
        return offering, "new", drift_list, 0

    # Check for drift (changes in data)
    drift = False

    if existing.name != course_data.name:
        drift_list.append(
            f"Offering {course_data.canvas_course_id}: name "
            f"'{existing.name}' -> '{course_data.name}'"
        )
        _record_change(
            session,
            EntityType.OFFERING,
            course_data.canvas_course_id,
            "name",
            existing.name,
            course_data.name,
            ingest_run_id,
            now,
        )
        existing.name = course_data.name
        drift = True
        change_count += 1

    if existing.code != course_data.code:
        drift_list.append(
            f"Offering {course_data.canvas_course_id}: code "
            f"'{existing.code}' -> '{course_data.code}'"
        )
        _record_change(
            session,
            EntityType.OFFERING,
            course_data.canvas_course_id,
            "code",
            existing.code,
            course_data.code,
            ingest_run_id,
            now,
        )
        existing.code = course_data.code
        drift = True
        change_count += 1

    if existing.workflow_state != course_data.workflow_state:
        drift_list.append(
            f"Offering {course_data.canvas_course_id}: state "
            f"'{existing.workflow_state}' -> '{course_data.workflow_state}'"
        )
        _record_change(
            session,
            EntityType.OFFERING,
            course_data.canvas_course_id,
            "workflow_state",
            existing.workflow_state,
            course_data.workflow_state,
            ingest_run_id,
            now,
        )
        existing.workflow_state = course_data.workflow_state
        drift = True
        change_count += 1

    if existing.term_id != term_id:
        drift_list.append(
            f"Offering {course_data.canvas_course_id}: term_id {existing.term_id} -> {term_id}"
        )
        _record_change(
            session,
            EntityType.OFFERING,
            course_data.canvas_course_id,
            "term_id",
            existing.term_id,
            term_id,
            ingest_run_id,
            now,
        )
        existing.term_id = term_id
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", drift_list, change_count

    return existing, "unchanged", drift_list, 0


def _upsert_user_enrollment(
    session: Session,
    enrollment_id: int,
    offering_id: int,
    role: str,
    enrollment_state: str,
    ingest_run_id: int,
) -> tuple[UserEnrollment, str, list[str], int]:
    """Upsert a user enrollment record.

    Returns:
        Tuple of (UserEnrollment, status, drift_list, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(UserEnrollment).where(UserEnrollment.canvas_enrollment_id == enrollment_id)
    existing = session.exec(stmt).first()

    now = _utcnow()
    drift_list: list[str] = []
    change_count = 0

    if existing is None:
        enrollment = UserEnrollment(
            canvas_enrollment_id=enrollment_id,
            offering_id=offering_id,
            role=role,
            enrollment_state=enrollment_state,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(enrollment)
        return enrollment, "new", drift_list, 0

    # Check for drift
    drift = False

    if existing.role != role:
        drift_list.append(f"Enrollment {enrollment_id}: role '{existing.role}' -> '{role}'")
        _record_change(
            session,
            EntityType.USER_ENROLLMENT,
            enrollment_id,
            "role",
            existing.role,
            role,
            ingest_run_id,
            now,
        )
        existing.role = role
        drift = True
        change_count += 1

    if existing.enrollment_state != enrollment_state:
        drift_list.append(
            f"Enrollment {enrollment_id}: state "
            f"'{existing.enrollment_state}' -> '{enrollment_state}'"
        )
        _record_change(
            session,
            EntityType.USER_ENROLLMENT,
            enrollment_id,
            "enrollment_state",
            existing.enrollment_state,
            enrollment_state,
            ingest_run_id,
            now,
        )
        existing.enrollment_state = enrollment_state
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", drift_list, change_count

    return existing, "unchanged", drift_list, 0


def ingest_catalog(
    client: CanvasClient,
    db_path: Path | str,
) -> IngestResult:
    """Ingest all courses visible to the authenticated user.

    Creates or updates:
    - Term records for each unique term
    - Offering records for each course
    - UserEnrollment records for the user's enrollment in each course

    Args:
        client: Configured CanvasClient instance.
        db_path: Path to the SQLite database.

    Returns:
        IngestResult with counts and any drift detected.
    """
    with get_session(db_path) as session:
        # Create ingest run record
        run = IngestRun(scope=IngestScope.CATALOG)
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.id is not None  # After commit, id is guaranteed to be set
        run_id: int = run.id

        try:
            # Fetch all courses from Canvas
            courses = client.list_my_courses()

            new_count = 0
            updated_count = 0
            unchanged_count = 0
            drift_count = 0
            all_drift: list[str] = []

            # Process each course
            terms_seen: dict[int, int] = {}  # canvas_term_id -> internal term_id

            for course_data in courses:
                # Handle term
                term_id: int | None = None
                if course_data.term_id:
                    if course_data.term_id in terms_seen:
                        term_id = terms_seen[course_data.term_id]
                    else:
                        # Try to get term details from course data
                        # (we already have term info from the include[]=term)
                        term_data = client.get_term_from_course(course_data.canvas_course_id)
                        if term_data:
                            term, term_status, term_changes = _upsert_term(
                                session, term_data, run_id
                            )
                            session.flush()  # Ensure term has an ID
                            assert term.id is not None  # After flush, id is set
                            term_id = term.id
                            terms_seen[course_data.term_id] = term_id
                            drift_count += term_changes
                            if term_status == "new":
                                new_count += 1
                            elif term_status == "updated":
                                updated_count += 1

                # Upsert offering
                offering, status, drift, offering_changes = _upsert_offering(
                    session, course_data, term_id, run_id
                )
                session.flush()  # Ensure offering has an ID
                assert offering.id is not None  # After flush, id is set
                all_drift.extend(drift)
                drift_count += offering_changes

                if status == "new":
                    new_count += 1
                elif status == "updated":
                    updated_count += 1
                else:
                    unchanged_count += 1

                # Upsert user enrollments for this course
                for enrollment_data in course_data.enrollments:
                    enroll, enroll_status, enroll_drift, enroll_changes = _upsert_user_enrollment(
                        session,
                        enrollment_id=enrollment_data.canvas_enrollment_id,
                        offering_id=offering.id,
                        role=enrollment_data.role,
                        enrollment_state=enrollment_data.enrollment_state,
                        ingest_run_id=run_id,
                    )
                    all_drift.extend(enroll_drift)
                    drift_count += enroll_changes

                    if enroll_status == "new":
                        new_count += 1
                    elif enroll_status == "updated":
                        updated_count += 1
                    else:
                        unchanged_count += 1

            # Update ingest run with results
            run.mark_completed(
                new_count=new_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                drift_count=drift_count,
            )
            session.commit()

            return IngestResult(
                run_id=run_id,
                new_count=new_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                drift_detected=all_drift,
            )

        except CanvasClientError as e:
            run.mark_failed(str(e))
            session.commit()
            return IngestResult(
                run_id=run_id,
                new_count=0,
                updated_count=0,
                unchanged_count=0,
                drift_detected=[],
                error=str(e),
            )
        except Exception as e:
            run.mark_failed(f"Unexpected error: {e}")
            session.commit()
            raise


def get_last_ingest_run(db_path: Path | str) -> IngestRun | None:
    """Get the most recent ingestion run.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        The most recent IngestRun or None if no runs exist.
    """
    with get_session(db_path) as session:
        stmt = select(IngestRun).order_by(IngestRun.started_at.desc()).limit(1)  # type: ignore[attr-defined]
        return session.exec(stmt).first()


def get_ingest_runs(
    db_path: Path | str,
    limit: int = 10,
    scope: IngestScope | None = None,
) -> list[IngestRun]:
    """Get recent ingestion runs.

    Args:
        db_path: Path to the SQLite database.
        limit: Maximum number of runs to return.
        scope: Optional filter by scope.

    Returns:
        List of IngestRun objects, most recent first.
    """
    with get_session(db_path) as session:
        stmt = select(IngestRun).order_by(IngestRun.started_at.desc()).limit(limit)  # type: ignore[attr-defined]
        if scope:
            stmt = stmt.where(IngestRun.scope == scope)
        return list(session.exec(stmt).all())


# =============================================================================
# Phase 3: Deep Ingestion (Sections, Enrollments, People)
# =============================================================================


def _upsert_section(
    session: Session,
    section_data: SectionData,
    offering_id: int,
    ingest_run_id: int,
) -> tuple[Section, str, list[str], int]:
    """Upsert a section record.

    Returns:
        Tuple of (Section, status, drift_list, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(Section).where(Section.canvas_section_id == section_data.canvas_section_id)
    existing = session.exec(stmt).first()

    now = _utcnow()
    drift_list: list[str] = []
    change_count = 0

    if existing is None:
        section = Section(
            canvas_section_id=section_data.canvas_section_id,
            offering_id=offering_id,
            name=section_data.name,
            sis_section_id=section_data.sis_section_id,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(section)
        return section, "new", drift_list, 0

    # Check for drift
    drift = False

    if existing.name != section_data.name:
        drift_list.append(
            f"Section {section_data.canvas_section_id}: name "
            f"'{existing.name}' -> '{section_data.name}'"
        )
        _record_change(
            session,
            EntityType.SECTION,
            section_data.canvas_section_id,
            "name",
            existing.name,
            section_data.name,
            ingest_run_id,
            now,
        )
        existing.name = section_data.name
        drift = True
        change_count += 1

    if existing.sis_section_id != section_data.sis_section_id:
        drift_list.append(
            f"Section {section_data.canvas_section_id}: sis_section_id "
            f"'{existing.sis_section_id}' -> '{section_data.sis_section_id}'"
        )
        _record_change(
            session,
            EntityType.SECTION,
            section_data.canvas_section_id,
            "sis_section_id",
            existing.sis_section_id,
            section_data.sis_section_id,
            ingest_run_id,
            now,
        )
        existing.sis_section_id = section_data.sis_section_id
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", drift_list, change_count

    return existing, "unchanged", drift_list, 0


def _upsert_person(
    session: Session,
    canvas_user_id: int,
    name: str,
    sortable_name: str | None,
    sis_user_id: str | None,
    login_id: str | None,
    ingest_run_id: int,
) -> tuple[Person, str, list[str], int]:
    """Upsert a person record.

    Returns:
        Tuple of (Person, status, drift_list, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(Person).where(Person.canvas_user_id == canvas_user_id)
    existing = session.exec(stmt).first()

    now = _utcnow()
    drift_list: list[str] = []
    change_count = 0

    if existing is None:
        person = Person(
            canvas_user_id=canvas_user_id,
            name=name,
            sortable_name=sortable_name,
            sis_user_id=sis_user_id,
            login_id=login_id,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(person)
        return person, "new", drift_list, 0

    # Check for drift
    drift = False

    if existing.name != name:
        drift_list.append(f"Person {canvas_user_id}: name '{existing.name}' -> '{name}'")
        _record_change(
            session,
            EntityType.PERSON,
            canvas_user_id,
            "name",
            existing.name,
            name,
            ingest_run_id,
            now,
        )
        existing.name = name
        drift = True
        change_count += 1

    if existing.sortable_name != sortable_name:
        _record_change(
            session,
            EntityType.PERSON,
            canvas_user_id,
            "sortable_name",
            existing.sortable_name,
            sortable_name,
            ingest_run_id,
            now,
        )
        existing.sortable_name = sortable_name
        drift = True
        change_count += 1

    if existing.sis_user_id != sis_user_id:
        _record_change(
            session,
            EntityType.PERSON,
            canvas_user_id,
            "sis_user_id",
            existing.sis_user_id,
            sis_user_id,
            ingest_run_id,
            now,
        )
        existing.sis_user_id = sis_user_id
        drift = True
        change_count += 1

    if existing.login_id != login_id:
        _record_change(
            session,
            EntityType.PERSON,
            canvas_user_id,
            "login_id",
            existing.login_id,
            login_id,
            ingest_run_id,
            now,
        )
        existing.login_id = login_id
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", drift_list, change_count

    return existing, "unchanged", drift_list, 0


def _upsert_enrollment(
    session: Session,
    enrollment_data: CourseEnrollmentData,
    offering_id: int,
    section_id: int | None,
    person_id: int,
    ingest_run_id: int,
) -> tuple[Enrollment, str, list[str], int]:
    """Upsert an enrollment record.

    Returns:
        Tuple of (Enrollment, status, drift_list, change_count) where status is 'new', 'updated', or 'unchanged'.
    """
    stmt = select(Enrollment).where(
        Enrollment.canvas_enrollment_id == enrollment_data.canvas_enrollment_id
    )
    existing = session.exec(stmt).first()

    now = _utcnow()
    drift_list: list[str] = []
    change_count = 0

    if existing is None:
        enrollment = Enrollment(
            canvas_enrollment_id=enrollment_data.canvas_enrollment_id,
            offering_id=offering_id,
            section_id=section_id,
            person_id=person_id,
            role=enrollment_data.role,
            enrollment_state=enrollment_data.enrollment_state,
            current_grade=enrollment_data.current_grade,
            current_score=enrollment_data.current_score,
            final_grade=enrollment_data.final_grade,
            final_score=enrollment_data.final_score,
            observed_at=now,
            last_seen_at=now,
        )
        session.add(enrollment)
        return enrollment, "new", drift_list, 0

    # Check for drift
    drift = False
    enrollment_id = enrollment_data.canvas_enrollment_id

    if existing.role != enrollment_data.role:
        drift_list.append(
            f"Enrollment {enrollment_id}: role '{existing.role}' -> '{enrollment_data.role}'"
        )
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "role",
            existing.role,
            enrollment_data.role,
            ingest_run_id,
            now,
        )
        existing.role = enrollment_data.role
        drift = True
        change_count += 1

    if existing.enrollment_state != enrollment_data.enrollment_state:
        drift_list.append(
            f"Enrollment {enrollment_id}: state "
            f"'{existing.enrollment_state}' -> '{enrollment_data.enrollment_state}'"
        )
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "enrollment_state",
            existing.enrollment_state,
            enrollment_data.enrollment_state,
            ingest_run_id,
            now,
        )
        existing.enrollment_state = enrollment_data.enrollment_state
        drift = True
        change_count += 1

    # Grade changes (track for drift)
    if existing.current_grade != enrollment_data.current_grade:
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "current_grade",
            existing.current_grade,
            enrollment_data.current_grade,
            ingest_run_id,
            now,
        )
        existing.current_grade = enrollment_data.current_grade
        drift = True
        change_count += 1

    if existing.current_score != enrollment_data.current_score:
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "current_score",
            existing.current_score,
            enrollment_data.current_score,
            ingest_run_id,
            now,
        )
        existing.current_score = enrollment_data.current_score
        drift = True
        change_count += 1

    if existing.final_grade != enrollment_data.final_grade:
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "final_grade",
            existing.final_grade,
            enrollment_data.final_grade,
            ingest_run_id,
            now,
        )
        existing.final_grade = enrollment_data.final_grade
        drift = True
        change_count += 1

    if existing.final_score != enrollment_data.final_score:
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "final_score",
            existing.final_score,
            enrollment_data.final_score,
            ingest_run_id,
            now,
        )
        existing.final_score = enrollment_data.final_score
        drift = True
        change_count += 1

    # Section change (unusual but possible)
    if existing.section_id != section_id:
        _record_change(
            session,
            EntityType.ENROLLMENT,
            enrollment_id,
            "section_id",
            existing.section_id,
            section_id,
            ingest_run_id,
            now,
        )
        existing.section_id = section_id
        drift = True
        change_count += 1

    existing.last_seen_at = now

    if drift:
        existing.observed_at = now
        return existing, "updated", drift_list, change_count

    return existing, "unchanged", drift_list, 0


def ingest_offering(
    client: CanvasClient,
    db_path: Path | str,
    canvas_course_id: int,
) -> IngestResult:
    """Deep ingest a specific offering (sections, enrollments, people).

    Creates or updates:
    - Section records for each section in the course
    - Person records for each user with an enrollment
    - Enrollment records for each enrollment (with grade data)

    Args:
        client: Configured CanvasClient instance.
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID to ingest.

    Returns:
        IngestResult with counts and any drift detected.
    """
    with get_session(db_path) as session:
        # First, verify the offering exists locally
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        offering = session.exec(stmt).first()

        if offering is None:
            # Need to run catalog ingest first or the offering doesn't exist
            return IngestResult(
                run_id=0,
                new_count=0,
                updated_count=0,
                unchanged_count=0,
                drift_detected=[],
                error=f"Offering {canvas_course_id} not found locally. "
                "Run 'cl ingest catalog' first to populate offerings.",
            )

        assert offering.id is not None
        offering_id: int = offering.id

        # Create ingest run record
        run = IngestRun(
            scope=IngestScope.OFFERING,
            scope_detail=str(canvas_course_id),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.id is not None
        run_id: int = run.id

        try:
            new_count = 0
            updated_count = 0
            unchanged_count = 0
            drift_count = 0
            all_drift: list[str] = []

            # Step 1: Fetch and upsert sections
            logger.info(f"Fetching sections for course {canvas_course_id}")
            sections = client.list_sections(canvas_course_id)

            section_map: dict[int, int] = {}  # canvas_section_id -> internal section_id

            for section_data in sections:
                section, status, drift, section_changes = _upsert_section(
                    session, section_data, offering_id, run_id
                )
                session.flush()
                assert section.id is not None
                section_map[section_data.canvas_section_id] = section.id
                all_drift.extend(drift)
                drift_count += section_changes

                if status == "new":
                    new_count += 1
                elif status == "updated":
                    updated_count += 1
                else:
                    unchanged_count += 1

            logger.info(f"Processed {len(sections)} sections")

            # Step 2: Fetch enrollments (includes user info)
            logger.info(f"Fetching enrollments for course {canvas_course_id}")
            enrollments = client.list_enrollments(canvas_course_id)

            logger.info(f"Processing {len(enrollments)} enrollments")

            for enrollment_data in enrollments:
                # Step 2a: Upsert the person
                person, person_status, person_drift, person_changes = _upsert_person(
                    session,
                    canvas_user_id=enrollment_data.user_id,
                    name=enrollment_data.user_name,
                    sortable_name=enrollment_data.user_sortable_name,
                    sis_user_id=enrollment_data.user_sis_id,
                    login_id=enrollment_data.user_login_id,
                    ingest_run_id=run_id,
                )
                session.flush()
                assert person.id is not None
                all_drift.extend(person_drift)
                drift_count += person_changes

                if person_status == "new":
                    new_count += 1
                elif person_status == "updated":
                    updated_count += 1

                # Step 2b: Map section_id
                section_id: int | None = None
                if enrollment_data.course_section_id:
                    section_id = section_map.get(enrollment_data.course_section_id)

                # Step 2c: Upsert the enrollment
                enrollment, enroll_status, enroll_drift, enroll_changes = _upsert_enrollment(
                    session,
                    enrollment_data,
                    offering_id=offering_id,
                    section_id=section_id,
                    person_id=person.id,
                    ingest_run_id=run_id,
                )
                all_drift.extend(enroll_drift)
                drift_count += enroll_changes

                if enroll_status == "new":
                    new_count += 1
                elif enroll_status == "updated":
                    updated_count += 1
                else:
                    unchanged_count += 1

            # Update ingest run with results
            run.mark_completed(
                new_count=new_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                drift_count=drift_count,
            )
            session.commit()

            return IngestResult(
                run_id=run_id,
                new_count=new_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                drift_detected=all_drift,
            )

        except CanvasNotFoundError as e:
            run.mark_failed(str(e))
            session.commit()
            return IngestResult(
                run_id=run_id,
                new_count=0,
                updated_count=0,
                unchanged_count=0,
                drift_detected=[],
                error=str(e),
            )
        except CanvasClientError as e:
            run.mark_failed(str(e))
            session.commit()
            return IngestResult(
                run_id=run_id,
                new_count=0,
                updated_count=0,
                unchanged_count=0,
                drift_detected=[],
                error=str(e),
            )
        except Exception as e:
            run.mark_failed(f"Unexpected error: {e}")
            session.commit()
            raise
