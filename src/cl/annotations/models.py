"""SQLModel models for annotations (declared truth).

Annotations store user-declared facts that coexist with observed Canvas data.
Key design principle: Annotations reference Canvas IDs (not internal FKs)
so they survive offering re-ingestion.

Phase 2: LeadInstructorAnnotation, InvolvementAnnotation
Phase 6: CourseAlias, CourseAliasOffering (deferred)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class AnnotationType(str, Enum):
    """Type of annotation."""

    LEAD_INSTRUCTOR = "lead_instructor"
    INVOLVEMENT = "involvement"
    COURSE_ALIAS = "course_alias"


class LeadDesignation(str, Enum):
    """Designation for lead instructor annotation.

    Both values represent the same concept (the person primarily
    responsible for the course), but users may prefer different terms.
    """

    LEAD = "lead"
    GRADE_RESPONSIBLE = "grade_responsible"


class LeadInstructorAnnotation(SQLModel, table=True):
    """Declare who is the lead/grade-responsible instructor for an offering.

    This annotation allows users to clarify who is primarily responsible
    when Canvas data shows multiple instructors or when the Canvas-reported
    role doesn't accurately reflect reality.

    References offerings and persons by Canvas IDs (not internal FKs) so
    annotations survive re-ingestion. The person_canvas_id may reference
    a user not yet in the local ledger (will be populated during deep ingestion).
    """

    __tablename__ = "lead_instructor_annotation"

    id: int | None = Field(default=None, primary_key=True)
    offering_canvas_id: int = Field(index=True)
    person_canvas_id: int = Field(index=True)
    designation: LeadDesignation = Field(default=LeadDesignation.LEAD)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "annotation_type": AnnotationType.LEAD_INSTRUCTOR.value,
            "offering_canvas_id": self.offering_canvas_id,
            "person_canvas_id": self.person_canvas_id,
            "designation": self.designation.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InvolvementAnnotation(SQLModel, table=True):
    """Classify the user's involvement in an offering.

    This annotation allows users to describe their actual involvement
    when the Canvas role doesn't tell the full story. For example:
    - "developed course" for a course you created but aren't listed as instructor
    - "guest lecturer" for a one-time teaching contribution
    - "co-instructor" to clarify shared teaching responsibility
    - "course coordinator" for administrative roles

    The classification field is free text to support any involvement type
    the user needs to record.

    References offerings by Canvas ID (not internal FK) so annotations
    survive re-ingestion.
    """

    __tablename__ = "involvement_annotation"

    id: int | None = Field(default=None, primary_key=True)
    offering_canvas_id: int = Field(index=True)
    classification: str  # Free text: "developed course", "guest lecturer", etc.
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "annotation_type": AnnotationType.INVOLVEMENT.value,
            "offering_canvas_id": self.offering_canvas_id,
            "classification": self.classification,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# Phase 6: Course Identity / Aliasing
# =============================================================================


class CourseAlias(SQLModel, table=True):
    """Group related offerings under a common alias name.

    Course aliases allow users to maintain continuity across:
    - Course renumbering (e.g., "CS 101" → "COMP 1010")
    - Special topics courses that represent different real courses
    - Local naming conventions or shorthand

    An alias groups multiple offerings so they can be queried together.
    This supports canonical query Q7: course identity continuity.

    Design decision: An offering can belong to multiple aliases. This supports
    cases like a course that is both renamed and also a special topics instance.
    """

    __tablename__ = "course_alias"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # The alias name (e.g., "BET 3510")
    description: str | None = None  # Optional description explaining the alias
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "annotation_type": AnnotationType.COURSE_ALIAS.value,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CourseAliasOffering(SQLModel, table=True):
    """Association between a CourseAlias and an Offering.

    This is a many-to-many relationship table. Each row links one alias
    to one offering via its Canvas course ID.

    References offerings by Canvas ID (not internal FK) so associations
    survive re-ingestion of offering data.
    """

    __tablename__ = "course_alias_offering"

    id: int | None = Field(default=None, primary_key=True)
    alias_id: int = Field(foreign_key="course_alias.id", index=True)
    offering_canvas_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "alias_id": self.alias_id,
            "offering_canvas_id": self.offering_canvas_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
