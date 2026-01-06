"""SQLModel models for the canvas-ledger database.

Phase 0: IngestRun for tracking ingestion runs.
Phase 1: Term, Offering, UserEnrollment for catalog ingestion.
Phase 3: Section, Person, Enrollment for deep ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class IngestScope(str, Enum):
    """Scope of an ingestion run."""

    CATALOG = "catalog"  # All visible courses
    OFFERING = "offering"  # Deep ingest for specific offering(s)


class IngestStatus(str, Enum):
    """Status of an ingestion run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestRun(SQLModel, table=True):
    """Track individual ingestion runs with metadata.

    Each run captures when data was fetched from Canvas,
    what scope was ingested, and summary counts.
    """

    __tablename__ = "ingest_run"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = Field(default=None)
    scope: IngestScope = Field(default=IngestScope.CATALOG)
    scope_detail: str | None = Field(
        default=None,
        description="Additional scope info, e.g., offering canvas_id for deep ingest",
    )
    status: IngestStatus = Field(default=IngestStatus.RUNNING)
    error_message: str | None = Field(default=None)

    # Summary counts
    new_count: int = Field(default=0)
    updated_count: int = Field(default=0)
    unchanged_count: int = Field(default=0)

    def mark_completed(
        self,
        new_count: int = 0,
        updated_count: int = 0,
        unchanged_count: int = 0,
    ) -> None:
        """Mark the ingestion run as completed with counts."""
        self.completed_at = _utcnow()
        self.status = IngestStatus.COMPLETED
        self.new_count = new_count
        self.updated_count = updated_count
        self.unchanged_count = unchanged_count

    def mark_failed(self, error_message: str) -> None:
        """Mark the ingestion run as failed with error message."""
        self.completed_at = _utcnow()
        self.status = IngestStatus.FAILED
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "scope": self.scope.value,
            "scope_detail": self.scope_detail,
            "status": self.status.value,
            "error_message": self.error_message,
            "new_count": self.new_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
        }


# =============================================================================
# Phase 1: Catalog Models
# =============================================================================


class Term(SQLModel, table=True):
    """Canvas term (enrollment term) metadata.

    Terms represent academic periods (semesters, quarters, etc.).
    A term may be null for courses without a term assignment.
    """

    __tablename__ = "term"

    id: int | None = Field(default=None, primary_key=True)
    canvas_term_id: int = Field(unique=True, index=True)
    name: str
    start_date: datetime | None = Field(default=None)
    end_date: datetime | None = Field(default=None)
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_term_id": self.canvas_term_id,
            "name": self.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class Offering(SQLModel, table=True):
    """Canvas course (offering) metadata.

    An offering represents a specific instance of a course in a term.
    This is the "course" from Canvas perspective, but we call it "offering"
    to distinguish from the abstract course concept.
    """

    __tablename__ = "offering"

    id: int | None = Field(default=None, primary_key=True)
    canvas_course_id: int = Field(unique=True, index=True)
    name: str
    code: str | None = Field(default=None)
    term_id: int | None = Field(default=None, foreign_key="term.id", index=True)
    workflow_state: str = Field(default="available")
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_course_id": self.canvas_course_id,
            "name": self.name,
            "code": self.code,
            "term_id": self.term_id,
            "workflow_state": self.workflow_state,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class UserEnrollment(SQLModel, table=True):
    """User's own enrollment in an offering.

    Tracks the authenticated user's enrollment roles across offerings.
    This is separate from general enrollments (Phase 3) which track
    all users in a course.
    """

    __tablename__ = "user_enrollment"

    id: int | None = Field(default=None, primary_key=True)
    canvas_enrollment_id: int = Field(unique=True, index=True)
    offering_id: int = Field(foreign_key="offering.id", index=True)
    role: str  # e.g., "teacher", "ta", "student", "designer", "observer"
    enrollment_state: str = Field(default="active")  # active, invited, completed, etc.
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_enrollment_id": self.canvas_enrollment_id,
            "offering_id": self.offering_id,
            "role": self.role,
            "enrollment_state": self.enrollment_state,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


# =============================================================================
# Phase 3: Deep Ingestion Models
# =============================================================================


class Section(SQLModel, table=True):
    """Canvas section within an offering.

    Sections represent subdivisions of a course, typically for
    organizational or scheduling purposes.
    """

    __tablename__ = "section"

    id: int | None = Field(default=None, primary_key=True)
    canvas_section_id: int = Field(unique=True, index=True)
    offering_id: int = Field(foreign_key="offering.id", index=True)
    name: str
    sis_section_id: str | None = Field(default=None, index=True)
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_section_id": self.canvas_section_id,
            "offering_id": self.offering_id,
            "name": self.name,
            "sis_section_id": self.sis_section_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class Person(SQLModel, table=True):
    """A person (user) observed through Canvas enrollments.

    Represents any user encountered during deep ingestion - students,
    instructors, TAs, etc. Identified primarily by Canvas user ID.
    """

    __tablename__ = "person"

    id: int | None = Field(default=None, primary_key=True)
    canvas_user_id: int = Field(unique=True, index=True)
    name: str
    sortable_name: str | None = Field(default=None)
    sis_user_id: str | None = Field(default=None, index=True)
    login_id: str | None = Field(default=None)
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_user_id": self.canvas_user_id,
            "name": self.name,
            "sortable_name": self.sortable_name,
            "sis_user_id": self.sis_user_id,
            "login_id": self.login_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class Enrollment(SQLModel, table=True):
    """A person's enrollment in an offering.

    Represents any enrollment (student, instructor, TA, etc.) with full
    enrollment details including section assignment and grade information.
    This is distinct from UserEnrollment which tracks only the current
    user's enrollments from catalog ingestion.
    """

    __tablename__ = "enrollment"

    id: int | None = Field(default=None, primary_key=True)
    canvas_enrollment_id: int = Field(unique=True, index=True)
    offering_id: int = Field(foreign_key="offering.id", index=True)
    section_id: int | None = Field(default=None, foreign_key="section.id", index=True)
    person_id: int = Field(foreign_key="person.id", index=True)
    role: str  # e.g., "StudentEnrollment", "TeacherEnrollment", etc.
    enrollment_state: str = Field(default="active")  # active, invited, completed, etc.
    # Grade fields (Canvas-reported, may be null)
    current_grade: str | None = Field(default=None)
    current_score: float | None = Field(default=None)
    final_grade: str | None = Field(default=None)
    final_score: float | None = Field(default=None)
    observed_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "canvas_enrollment_id": self.canvas_enrollment_id,
            "offering_id": self.offering_id,
            "section_id": self.section_id,
            "person_id": self.person_id,
            "role": self.role,
            "enrollment_state": self.enrollment_state,
            "current_grade": self.current_grade,
            "current_score": self.current_score,
            "final_grade": self.final_grade,
            "final_score": self.final_score,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }
