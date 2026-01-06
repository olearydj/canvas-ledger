"""Query implementations for canvas-ledger.

Provides read-only queries against the local ledger database.
Queries merge observed data with declared annotations where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from cl.annotations.models import InvolvementAnnotation, LeadInstructorAnnotation
from cl.ledger.models import Enrollment, Offering, Person, Section, Term, UserEnrollment
from cl.ledger.store import get_session

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class TimelineEntry:
    """A single entry in the user's involvement timeline.

    Contains both observed data (from Canvas) and declared data (from annotations).
    The distinction is made explicit through separate fields.
    """

    canvas_course_id: int
    offering_name: str
    offering_code: str | None
    workflow_state: str
    term_name: str | None
    term_start_date: datetime | None
    # Observed data from Canvas
    roles: list[str]  # User's observed Canvas roles in this offering
    enrollment_states: list[str]  # States for each enrollment
    observed_at: datetime
    last_seen_at: datetime
    # Declared data from annotations
    declared_involvement: str | None = None  # From InvolvementAnnotation

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "offering_name": self.offering_name,
            "offering_code": self.offering_code,
            "workflow_state": self.workflow_state,
            "term_name": self.term_name,
            "term_start_date": (self.term_start_date.isoformat() if self.term_start_date else None),
            "observed_roles": self.roles,
            "enrollment_states": self.enrollment_states,
            "declared_involvement": self.declared_involvement,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


@dataclass
class OfferingResponsibility:
    """Responsibility information for an offering.

    Combines observed Canvas data with declared annotations to show
    who is responsible for the course.
    """

    canvas_course_id: int
    offering_name: str
    offering_code: str | None
    # Observed data from Canvas enrollments (for user's own roles)
    observed_instructors: list[dict[str, Any]] = field(default_factory=list)
    # Declared data from annotations
    declared_lead: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "offering_name": self.offering_name,
            "offering_code": self.offering_code,
            "observed_instructors": self.observed_instructors,
            "declared_lead": self.declared_lead,
        }


def get_my_timeline(
    db_path: Path | str,
    term_filter: str | None = None,
    role_filter: str | None = None,
) -> list[TimelineEntry]:
    """Get the user's involvement timeline.

    Returns all offerings the user has enrollments in, sorted by term
    (most recent first) then by offering name. Includes both observed
    roles from Canvas and declared involvement from annotations.

    Args:
        db_path: Path to the SQLite database.
        term_filter: Optional filter by term name (case-insensitive contains).
        role_filter: Optional filter by role (exact match).

    Returns:
        List of TimelineEntry objects representing the user's involvement.
    """
    with get_session(db_path) as session:
        return _get_my_timeline_impl(session, term_filter, role_filter)


def _get_my_timeline_impl(
    session: Session,
    term_filter: str | None = None,
    role_filter: str | None = None,
) -> list[TimelineEntry]:
    """Implementation of get_my_timeline that takes an existing session."""
    # Get all user enrollments with their offerings
    stmt = (
        select(UserEnrollment, Offering, Term)
        .join(Offering, UserEnrollment.offering_id == Offering.id)  # type: ignore[arg-type]
        .outerjoin(Term, Offering.term_id == Term.id)  # type: ignore[arg-type]
    )

    if role_filter:
        stmt = stmt.where(UserEnrollment.role == role_filter)

    if term_filter:
        # Case-insensitive contains match on term name
        stmt = stmt.where(Term.name.icontains(term_filter))  # type: ignore[attr-defined]

    results = session.exec(stmt).all()

    # Group enrollments by offering
    offerings_map: dict[int, dict[str, Any]] = {}

    for enrollment, offering, term in results:
        course_id = offering.canvas_course_id

        if course_id not in offerings_map:
            offerings_map[course_id] = {
                "offering": offering,
                "term": term,
                "roles": [],
                "enrollment_states": [],
            }

        offerings_map[course_id]["roles"].append(enrollment.role)
        offerings_map[course_id]["enrollment_states"].append(enrollment.enrollment_state)

    # Get all involvement annotations and build a lookup
    inv_stmt = select(InvolvementAnnotation)
    involvement_annotations = {
        ann.offering_canvas_id: ann.classification for ann in session.exec(inv_stmt).all()
    }

    # Convert to TimelineEntry objects
    entries: list[TimelineEntry] = []

    for course_id, data in offerings_map.items():
        offering = data["offering"]
        term = data["term"]

        entries.append(
            TimelineEntry(
                canvas_course_id=course_id,
                offering_name=offering.name,
                offering_code=offering.code,
                workflow_state=offering.workflow_state,
                term_name=term.name if term else None,
                term_start_date=term.start_date if term else None,
                roles=data["roles"],
                enrollment_states=data["enrollment_states"],
                observed_at=offering.observed_at,
                last_seen_at=offering.last_seen_at,
                declared_involvement=involvement_annotations.get(course_id),
            )
        )

    # Sort by term start date (descending, nulls last), then by name
    def sort_key(entry: TimelineEntry) -> tuple[float, str]:
        # Use a very old date for None to push to end
        date = entry.term_start_date or datetime.min.replace(tzinfo=None)
        if hasattr(date, "tzinfo") and date.tzinfo:
            date = date.replace(tzinfo=None)
        return (-date.timestamp() if date != datetime.min else float("inf"), entry.offering_name)

    entries.sort(key=sort_key)

    return entries


def get_offering_responsibility(
    db_path: Path | str,
    canvas_course_id: int,
) -> OfferingResponsibility | None:
    """Get responsibility information for an offering.

    Returns both observed instructors (from Canvas enrollments) and
    declared lead instructor (from LeadInstructorAnnotation).

    If deep ingestion has been run for this offering, instructors are pulled
    from the Enrollment table (all course instructors). Otherwise, falls back
    to UserEnrollment (the current user's own enrollments).

    Args:
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID.

    Returns:
        OfferingResponsibility object or None if offering not found.
    """
    with get_session(db_path) as session:
        # Get the offering
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        offering = session.exec(stmt).first()

        if offering is None:
            return None

        # Define instructor roles
        instructor_roles = {
            "TeacherEnrollment",
            "TaEnrollment",
            "DesignerEnrollment",
            "teacher",
            "ta",
            "designer",
        }

        # First try to get instructors from deep ingestion (Enrollment table)
        deep_enrollment_stmt = (
            select(Enrollment, Person)
            .join(Person, Enrollment.person_id == Person.id)  # type: ignore[arg-type]
            .where(Enrollment.offering_id == offering.id)
            .where(Enrollment.role.in_(instructor_roles))  # type: ignore[attr-defined]
        )
        deep_results = session.exec(deep_enrollment_stmt).all()

        if deep_results:
            # Use deep ingestion data (has person names)
            observed_instructors = [
                {
                    "canvas_user_id": person.canvas_user_id,
                    "person_name": person.name,
                    "role": enrollment.role,
                    "enrollment_state": enrollment.enrollment_state,
                    "source": "enrollment",
                }
                for enrollment, person in deep_results
            ]
        else:
            # Fall back to UserEnrollment (user's own enrollments)
            user_enrollment_stmt = (
                select(UserEnrollment)
                .where(UserEnrollment.offering_id == offering.id)
                .where(UserEnrollment.role.in_(instructor_roles))  # type: ignore[attr-defined]
            )
            user_enrollments = session.exec(user_enrollment_stmt).all()

            observed_instructors = [
                {
                    "role": e.role,
                    "enrollment_state": e.enrollment_state,
                    "source": "user_enrollment",
                }
                for e in user_enrollments
            ]

        # Get declared lead instructor
        lead_stmt = select(LeadInstructorAnnotation).where(
            LeadInstructorAnnotation.offering_canvas_id == canvas_course_id
        )
        lead_annotation = session.exec(lead_stmt).first()

        declared_lead = None
        if lead_annotation:
            # Try to get person name if they exist in the ledger
            person_name = None
            person_stmt = select(Person).where(
                Person.canvas_user_id == lead_annotation.person_canvas_id
            )
            person = session.exec(person_stmt).first()
            if person:
                person_name = person.name

            declared_lead = {
                "person_canvas_id": lead_annotation.person_canvas_id,
                "person_name": person_name,
                "designation": lead_annotation.designation.value,
                "created_at": lead_annotation.created_at.isoformat()
                if lead_annotation.created_at
                else None,
            }

        return OfferingResponsibility(
            canvas_course_id=canvas_course_id,
            offering_name=offering.name,
            offering_code=offering.code,
            observed_instructors=observed_instructors,
            declared_lead=declared_lead,
        )


def get_all_offerings(
    db_path: Path | str,
    include_inactive: bool = False,
) -> list[Offering]:
    """Get all offerings in the ledger.

    Args:
        db_path: Path to the SQLite database.
        include_inactive: If True, include offerings with non-available states.

    Returns:
        List of Offering objects.
    """
    with get_session(db_path) as session:
        stmt = select(Offering)

        if not include_inactive:
            stmt = stmt.where(Offering.workflow_state == "available")

        stmt = stmt.order_by(Offering.name)
        return list(session.exec(stmt).all())


def get_offering_by_canvas_id(
    db_path: Path | str,
    canvas_course_id: int,
) -> Offering | None:
    """Get an offering by its Canvas course ID.

    Args:
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID.

    Returns:
        Offering object or None if not found.
    """
    with get_session(db_path) as session:
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        return session.exec(stmt).first()


def get_offerings_with_terms(db_path: Path | str) -> list[dict[str, Any]]:
    """Get all offerings with their term information.

    Returns offering data suitable for export.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        List of dictionaries with offering and term data.
    """
    with get_session(db_path) as session:
        stmt = (
            select(Offering, Term)
            .outerjoin(Term, Offering.term_id == Term.id)  # type: ignore[arg-type]
            .order_by(Offering.name)
        )

        results = session.exec(stmt).all()

        return [
            {
                "canvas_course_id": offering.canvas_course_id,
                "name": offering.name,
                "code": offering.code,
                "workflow_state": offering.workflow_state,
                "term_name": term.name if term else None,
                "term_start_date": (
                    term.start_date.isoformat() if term and term.start_date else None
                ),
                "term_end_date": (term.end_date.isoformat() if term and term.end_date else None),
                "observed_at": (offering.observed_at.isoformat() if offering.observed_at else None),
                "last_seen_at": (
                    offering.last_seen_at.isoformat() if offering.last_seen_at else None
                ),
            }
            for offering, term in results
        ]


# =============================================================================
# Phase 3: Deep Ingestion Queries
# =============================================================================


@dataclass
class RosterEntry:
    """A single entry in an offering's roster.

    Contains person and enrollment information for display.
    """

    canvas_user_id: int
    person_name: str
    sortable_name: str | None
    section_name: str | None
    section_canvas_id: int | None
    role: str
    enrollment_state: str
    current_grade: str | None = None
    current_score: float | None = None
    final_grade: str | None = None
    final_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_user_id": self.canvas_user_id,
            "person_name": self.person_name,
            "sortable_name": self.sortable_name,
            "section_name": self.section_name,
            "section_canvas_id": self.section_canvas_id,
            "role": self.role,
            "enrollment_state": self.enrollment_state,
            "current_grade": self.current_grade,
            "current_score": self.current_score,
            "final_grade": self.final_grade,
            "final_score": self.final_score,
        }


@dataclass
class PersonHistoryEntry:
    """A single entry in a person's enrollment history.

    Contains offering, section, and enrollment information.
    """

    canvas_course_id: int
    offering_name: str
    offering_code: str | None
    term_name: str | None
    term_start_date: datetime | None
    section_name: str | None
    section_canvas_id: int | None
    role: str
    enrollment_state: str
    current_grade: str | None = None
    current_score: float | None = None
    final_grade: str | None = None
    final_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "offering_name": self.offering_name,
            "offering_code": self.offering_code,
            "term_name": self.term_name,
            "term_start_date": (self.term_start_date.isoformat() if self.term_start_date else None),
            "section_name": self.section_name,
            "section_canvas_id": self.section_canvas_id,
            "role": self.role,
            "enrollment_state": self.enrollment_state,
            "current_grade": self.current_grade,
            "current_score": self.current_score,
            "final_grade": self.final_grade,
            "final_score": self.final_score,
        }


@dataclass
class OfferingRoster:
    """Complete roster for an offering.

    Contains offering metadata and enrollments grouped by section.
    """

    canvas_course_id: int
    offering_name: str
    offering_code: str | None
    sections: dict[str, list[RosterEntry]]  # section_name -> enrollments

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "offering_name": self.offering_name,
            "offering_code": self.offering_code,
            "sections": {
                section_name: [e.to_dict() for e in entries]
                for section_name, entries in self.sections.items()
            },
        }


def get_offering_roster(
    db_path: Path | str,
    canvas_course_id: int,
) -> OfferingRoster | None:
    """Get the roster for an offering, grouped by section.

    Returns all enrollments for the offering with person and section information.

    Args:
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID.

    Returns:
        OfferingRoster object or None if offering not found.
    """
    with get_session(db_path) as session:
        # Get the offering
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        offering = session.exec(stmt).first()

        if offering is None:
            return None

        # Get all enrollments for this offering with person and section info
        enrollment_stmt = (
            select(Enrollment, Person, Section)
            .join(Person, Enrollment.person_id == Person.id)  # type: ignore[arg-type]
            .outerjoin(Section, Enrollment.section_id == Section.id)  # type: ignore[arg-type]
            .where(Enrollment.offering_id == offering.id)
            .order_by(Section.name, Person.sortable_name)  # type: ignore[arg-type]
        )

        results = session.exec(enrollment_stmt).all()

        # Group by section
        sections: dict[str, list[RosterEntry]] = {}

        for enrollment, person, section in results:
            section_name = section.name if section else "(No Section)"

            if section_name not in sections:
                sections[section_name] = []

            sections[section_name].append(
                RosterEntry(
                    canvas_user_id=person.canvas_user_id,
                    person_name=person.name,
                    sortable_name=person.sortable_name,
                    section_name=section.name if section else None,
                    section_canvas_id=section.canvas_section_id if section else None,
                    role=enrollment.role,
                    enrollment_state=enrollment.enrollment_state,
                    current_grade=enrollment.current_grade,
                    current_score=enrollment.current_score,
                    final_grade=enrollment.final_grade,
                    final_score=enrollment.final_score,
                )
            )

        return OfferingRoster(
            canvas_course_id=canvas_course_id,
            offering_name=offering.name,
            offering_code=offering.code,
            sections=sections,
        )


def get_person_history(
    db_path: Path | str,
    canvas_user_id: int,
) -> list[PersonHistoryEntry]:
    """Get the enrollment history for a person across all ingested offerings.

    Returns all enrollments for the person with offering, term, and section info.

    Args:
        db_path: Path to the SQLite database.
        canvas_user_id: Canvas user ID.

    Returns:
        List of PersonHistoryEntry objects, sorted by term (most recent first).
    """
    with get_session(db_path) as session:
        # Get the person
        stmt = select(Person).where(Person.canvas_user_id == canvas_user_id)
        person = session.exec(stmt).first()

        if person is None:
            return []

        # Get all enrollments for this person with offering, term, and section info
        enrollment_stmt = (
            select(Enrollment, Offering, Term, Section)
            .join(Offering, Enrollment.offering_id == Offering.id)  # type: ignore[arg-type]
            .outerjoin(Term, Offering.term_id == Term.id)  # type: ignore[arg-type]
            .outerjoin(Section, Enrollment.section_id == Section.id)  # type: ignore[arg-type]
            .where(Enrollment.person_id == person.id)
        )

        results = session.exec(enrollment_stmt).all()

        entries: list[PersonHistoryEntry] = []

        for enrollment, offering, term, section in results:
            entries.append(
                PersonHistoryEntry(
                    canvas_course_id=offering.canvas_course_id,
                    offering_name=offering.name,
                    offering_code=offering.code,
                    term_name=term.name if term else None,
                    term_start_date=term.start_date if term else None,
                    section_name=section.name if section else None,
                    section_canvas_id=section.canvas_section_id if section else None,
                    role=enrollment.role,
                    enrollment_state=enrollment.enrollment_state,
                    current_grade=enrollment.current_grade,
                    current_score=enrollment.current_score,
                    final_grade=enrollment.final_grade,
                    final_score=enrollment.final_score,
                )
            )

        # Sort by term start date (descending, nulls last), then by offering name
        def sort_key(entry: PersonHistoryEntry) -> tuple[float, str]:
            date = entry.term_start_date or datetime.min.replace(tzinfo=None)
            if hasattr(date, "tzinfo") and date.tzinfo:
                date = date.replace(tzinfo=None)
            return (
                -date.timestamp() if date != datetime.min else float("inf"),
                entry.offering_name,
            )

        entries.sort(key=sort_key)

        return entries


def get_person_by_canvas_id(
    db_path: Path | str,
    canvas_user_id: int,
) -> Person | None:
    """Get a person by their Canvas user ID.

    Args:
        db_path: Path to the SQLite database.
        canvas_user_id: Canvas user ID.

    Returns:
        Person object or None if not found.
    """
    with get_session(db_path) as session:
        stmt = select(Person).where(Person.canvas_user_id == canvas_user_id)
        return session.exec(stmt).first()


def get_offering_instructors(
    db_path: Path | str,
    canvas_course_id: int,
) -> list[dict[str, Any]]:
    """Get all instructors for an offering from the Enrollment table.

    Returns instructors (TeacherEnrollment, TaEnrollment, DesignerEnrollment)
    with person information.

    Args:
        db_path: Path to the SQLite database.
        canvas_course_id: Canvas course ID.

    Returns:
        List of instructor dictionaries with person and enrollment info.
    """
    with get_session(db_path) as session:
        # Get the offering
        stmt = select(Offering).where(Offering.canvas_course_id == canvas_course_id)
        offering = session.exec(stmt).first()

        if offering is None:
            return []

        # Define instructor roles
        instructor_roles = {
            "TeacherEnrollment",
            "TaEnrollment",
            "DesignerEnrollment",
            "teacher",
            "ta",
            "designer",
        }

        # Get instructor enrollments
        enrollment_stmt = (
            select(Enrollment, Person)
            .join(Person, Enrollment.person_id == Person.id)  # type: ignore[arg-type]
            .where(Enrollment.offering_id == offering.id)
            .where(Enrollment.role.in_(instructor_roles))  # type: ignore[attr-defined]
        )

        results = session.exec(enrollment_stmt).all()

        return [
            {
                "canvas_user_id": person.canvas_user_id,
                "person_name": person.name,
                "role": enrollment.role,
                "enrollment_state": enrollment.enrollment_state,
                "source": "enrollment",  # Distinguishes from user_enrollment
            }
            for enrollment, person in results
        ]
