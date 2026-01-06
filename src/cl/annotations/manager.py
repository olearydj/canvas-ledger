"""Annotation manager for CRUD operations on declared truth.

Provides functions for adding, listing, and removing annotations
(lead instructor designations and involvement classifications).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from cl.annotations.models import (
    CourseAlias,
    CourseAliasOffering,
    InvolvementAnnotation,
    LeadDesignation,
    LeadInstructorAnnotation,
)
from cl.ledger.models import Offering
from cl.ledger.store import get_session

if TYPE_CHECKING:
    from pathlib import Path


class AnnotationError(Exception):
    """Base exception for annotation operations."""

    pass


class OfferingNotFoundError(AnnotationError):
    """Raised when an offering is not found in the local ledger."""

    def __init__(self, canvas_course_id: int) -> None:
        self.canvas_course_id = canvas_course_id
        super().__init__(
            f"Offering with Canvas ID {canvas_course_id} not found in local ledger. "
            "Run 'cl ingest catalog' first."
        )


class AnnotationNotFoundError(AnnotationError):
    """Raised when an annotation is not found."""

    def __init__(self, annotation_id: int, annotation_type: str) -> None:
        self.annotation_id = annotation_id
        self.annotation_type = annotation_type
        super().__init__(f"{annotation_type} annotation with ID {annotation_id} not found.")


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def _validate_offering_exists(session: Session, offering_canvas_id: int) -> Offering:
    """Validate that an offering exists in the local ledger.

    Args:
        session: Database session.
        offering_canvas_id: Canvas course ID.

    Returns:
        The Offering object.

    Raises:
        OfferingNotFoundError: If the offering is not found.
    """
    stmt = select(Offering).where(Offering.canvas_course_id == offering_canvas_id)
    offering = session.exec(stmt).first()
    if offering is None:
        raise OfferingNotFoundError(offering_canvas_id)
    return offering


def add_lead_instructor(
    db_path: Path | str,
    offering_canvas_id: int,
    person_canvas_id: int,
    designation: str = "lead",
) -> LeadInstructorAnnotation:
    """Add or update a lead instructor annotation for an offering.

    If an annotation already exists for this offering/person combination,
    it will be updated with the new designation.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Canvas course ID.
        person_canvas_id: Canvas user ID of the lead instructor.
        designation: Either "lead" or "grade_responsible".

    Returns:
        The created or updated LeadInstructorAnnotation.

    Raises:
        OfferingNotFoundError: If the offering is not found locally.
        ValueError: If the designation is invalid.
    """
    try:
        desig = LeadDesignation(designation)
    except ValueError:
        valid_values = [d.value for d in LeadDesignation]
        raise ValueError(
            f"Invalid designation '{designation}'. Must be one of: {valid_values}"
        ) from None

    with get_session(db_path) as session:
        # Validate offering exists
        _validate_offering_exists(session, offering_canvas_id)

        # Check if annotation already exists for this offering/person
        stmt = select(LeadInstructorAnnotation).where(
            LeadInstructorAnnotation.offering_canvas_id == offering_canvas_id,
            LeadInstructorAnnotation.person_canvas_id == person_canvas_id,
        )
        existing = session.exec(stmt).first()

        if existing:
            # Update existing annotation
            existing.designation = desig
            existing.updated_at = _utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        else:
            # Create new annotation
            annotation = LeadInstructorAnnotation(
                offering_canvas_id=offering_canvas_id,
                person_canvas_id=person_canvas_id,
                designation=desig,
            )
            session.add(annotation)
            session.commit()
            session.refresh(annotation)
            return annotation


def add_involvement(
    db_path: Path | str,
    offering_canvas_id: int,
    classification: str,
) -> InvolvementAnnotation:
    """Add or update an involvement annotation for an offering.

    If an involvement annotation already exists for this offering,
    it will be updated with the new classification.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Canvas course ID.
        classification: Free-text involvement classification.

    Returns:
        The created or updated InvolvementAnnotation.

    Raises:
        OfferingNotFoundError: If the offering is not found locally.
    """
    with get_session(db_path) as session:
        # Validate offering exists
        _validate_offering_exists(session, offering_canvas_id)

        # Check if annotation already exists for this offering
        stmt = select(InvolvementAnnotation).where(
            InvolvementAnnotation.offering_canvas_id == offering_canvas_id
        )
        existing = session.exec(stmt).first()

        if existing:
            # Update existing annotation
            existing.classification = classification
            existing.updated_at = _utcnow()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        else:
            # Create new annotation
            annotation = InvolvementAnnotation(
                offering_canvas_id=offering_canvas_id,
                classification=classification,
            )
            session.add(annotation)
            session.commit()
            session.refresh(annotation)
            return annotation


def list_annotations(
    db_path: Path | str,
    offering_canvas_id: int | None = None,
) -> list[dict[str, Any]]:
    """List annotations, optionally filtered by offering.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Optional Canvas course ID to filter by.

    Returns:
        List of annotation dictionaries (both types combined).
    """
    with get_session(db_path) as session:
        results: list[dict[str, Any]] = []

        # Get lead instructor annotations
        lead_stmt = select(LeadInstructorAnnotation)
        if offering_canvas_id is not None:
            lead_stmt = lead_stmt.where(
                LeadInstructorAnnotation.offering_canvas_id == offering_canvas_id
            )
        lead_stmt = lead_stmt.order_by(LeadInstructorAnnotation.created_at)  # type: ignore[arg-type]

        for lead_ann in session.exec(lead_stmt).all():
            results.append(lead_ann.to_dict())

        # Get involvement annotations
        inv_stmt = select(InvolvementAnnotation)
        if offering_canvas_id is not None:
            inv_stmt = inv_stmt.where(
                InvolvementAnnotation.offering_canvas_id == offering_canvas_id
            )
        inv_stmt = inv_stmt.order_by(InvolvementAnnotation.created_at)  # type: ignore[arg-type]

        for inv_ann in session.exec(inv_stmt).all():
            results.append(inv_ann.to_dict())

        return results


def get_lead_instructor_annotations(
    db_path: Path | str,
    offering_canvas_id: int | None = None,
) -> list[LeadInstructorAnnotation]:
    """Get lead instructor annotations, optionally filtered by offering.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Optional Canvas course ID to filter by.

    Returns:
        List of LeadInstructorAnnotation objects.
    """
    with get_session(db_path) as session:
        stmt = select(LeadInstructorAnnotation)
        if offering_canvas_id is not None:
            stmt = stmt.where(LeadInstructorAnnotation.offering_canvas_id == offering_canvas_id)
        stmt = stmt.order_by(LeadInstructorAnnotation.created_at)  # type: ignore[arg-type]
        return list(session.exec(stmt).all())


def get_involvement_annotations(
    db_path: Path | str,
    offering_canvas_id: int | None = None,
) -> list[InvolvementAnnotation]:
    """Get involvement annotations, optionally filtered by offering.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Optional Canvas course ID to filter by.

    Returns:
        List of InvolvementAnnotation objects.
    """
    with get_session(db_path) as session:
        stmt = select(InvolvementAnnotation)
        if offering_canvas_id is not None:
            stmt = stmt.where(InvolvementAnnotation.offering_canvas_id == offering_canvas_id)
        stmt = stmt.order_by(InvolvementAnnotation.created_at)  # type: ignore[arg-type]
        return list(session.exec(stmt).all())


def remove_lead_instructor_annotation(
    db_path: Path | str,
    annotation_id: int,
) -> None:
    """Remove a lead instructor annotation.

    Args:
        db_path: Path to the SQLite database.
        annotation_id: ID of the annotation to remove.

    Raises:
        AnnotationNotFoundError: If the annotation is not found.
    """
    with get_session(db_path) as session:
        stmt = select(LeadInstructorAnnotation).where(LeadInstructorAnnotation.id == annotation_id)
        annotation = session.exec(stmt).first()
        if annotation is None:
            raise AnnotationNotFoundError(annotation_id, "Lead instructor")
        session.delete(annotation)
        session.commit()


def remove_involvement_annotation(
    db_path: Path | str,
    annotation_id: int,
) -> None:
    """Remove an involvement annotation.

    Args:
        db_path: Path to the SQLite database.
        annotation_id: ID of the annotation to remove.

    Raises:
        AnnotationNotFoundError: If the annotation is not found.
    """
    with get_session(db_path) as session:
        stmt = select(InvolvementAnnotation).where(InvolvementAnnotation.id == annotation_id)
        annotation = session.exec(stmt).first()
        if annotation is None:
            raise AnnotationNotFoundError(annotation_id, "Involvement")
        session.delete(annotation)
        session.commit()


def remove_annotation(
    db_path: Path | str,
    annotation_id: int,
    annotation_type: str,
) -> None:
    """Remove an annotation by ID and type.

    Args:
        db_path: Path to the SQLite database.
        annotation_id: ID of the annotation to remove.
        annotation_type: Type of annotation ("lead_instructor" or "involvement").

    Raises:
        AnnotationNotFoundError: If the annotation is not found.
        ValueError: If the annotation type is invalid.
    """
    if annotation_type == "lead_instructor":
        remove_lead_instructor_annotation(db_path, annotation_id)
    elif annotation_type == "involvement":
        remove_involvement_annotation(db_path, annotation_id)
    else:
        raise ValueError(
            f"Invalid annotation type '{annotation_type}'. "
            "Must be 'lead_instructor' or 'involvement'."
        )


# =============================================================================
# Phase 6: Course Alias Operations
# =============================================================================


class AliasNotFoundError(AnnotationError):
    """Raised when a course alias is not found."""

    def __init__(self, alias_name: str) -> None:
        self.alias_name = alias_name
        super().__init__(f"Alias '{alias_name}' not found.")


class AliasAlreadyExistsError(AnnotationError):
    """Raised when trying to create an alias that already exists."""

    def __init__(self, alias_name: str) -> None:
        self.alias_name = alias_name
        super().__init__(f"Alias '{alias_name}' already exists.")


class OfferingAlreadyInAliasError(AnnotationError):
    """Raised when an offering is already in the specified alias."""

    def __init__(self, alias_name: str, offering_canvas_id: int) -> None:
        self.alias_name = alias_name
        self.offering_canvas_id = offering_canvas_id
        super().__init__(f"Offering {offering_canvas_id} is already in alias '{alias_name}'.")


class OfferingNotInAliasError(AnnotationError):
    """Raised when an offering is not in the specified alias."""

    def __init__(self, alias_name: str, offering_canvas_id: int) -> None:
        self.alias_name = alias_name
        self.offering_canvas_id = offering_canvas_id
        super().__init__(f"Offering {offering_canvas_id} is not in alias '{alias_name}'.")


def create_alias(
    db_path: Path | str,
    name: str,
    offering_canvas_ids: list[int] | None = None,
    description: str | None = None,
) -> CourseAlias:
    """Create a new course alias with optional initial offerings.

    Args:
        db_path: Path to the SQLite database.
        name: Name for the alias (must be unique).
        offering_canvas_ids: Optional list of Canvas course IDs to add initially.
        description: Optional description of the alias.

    Returns:
        The created CourseAlias.

    Raises:
        AliasAlreadyExistsError: If an alias with this name already exists.
        OfferingNotFoundError: If any of the offerings are not found locally.
    """
    with get_session(db_path) as session:
        # Check if alias already exists
        existing_stmt = select(CourseAlias).where(CourseAlias.name == name)
        if session.exec(existing_stmt).first() is not None:
            raise AliasAlreadyExistsError(name)

        # Validate all offerings exist (if provided)
        if offering_canvas_ids:
            for canvas_id in offering_canvas_ids:
                _validate_offering_exists(session, canvas_id)

        # Create the alias
        alias = CourseAlias(
            name=name,
            description=description,
        )
        session.add(alias)
        session.flush()  # Get the ID

        # Add initial offerings
        if offering_canvas_ids:
            for canvas_id in offering_canvas_ids:
                association = CourseAliasOffering(
                    alias_id=alias.id,
                    offering_canvas_id=canvas_id,
                )
                session.add(association)

        session.commit()
        session.refresh(alias)
        return alias


def add_to_alias(
    db_path: Path | str,
    alias_name: str,
    offering_canvas_id: int,
) -> CourseAliasOffering:
    """Add an offering to an existing alias.

    Args:
        db_path: Path to the SQLite database.
        alias_name: Name of the alias.
        offering_canvas_id: Canvas course ID of the offering to add.

    Returns:
        The created CourseAliasOffering association.

    Raises:
        AliasNotFoundError: If the alias is not found.
        OfferingNotFoundError: If the offering is not found locally.
        OfferingAlreadyInAliasError: If the offering is already in the alias.
    """
    with get_session(db_path) as session:
        # Get the alias
        alias_stmt = select(CourseAlias).where(CourseAlias.name == alias_name)
        alias = session.exec(alias_stmt).first()
        if alias is None:
            raise AliasNotFoundError(alias_name)

        # Validate offering exists
        _validate_offering_exists(session, offering_canvas_id)

        # Check if already in alias
        existing_stmt = select(CourseAliasOffering).where(
            CourseAliasOffering.alias_id == alias.id,
            CourseAliasOffering.offering_canvas_id == offering_canvas_id,
        )
        if session.exec(existing_stmt).first() is not None:
            raise OfferingAlreadyInAliasError(alias_name, offering_canvas_id)

        # Create association
        association = CourseAliasOffering(
            alias_id=alias.id,
            offering_canvas_id=offering_canvas_id,
        )
        session.add(association)

        # Update alias timestamp
        alias.updated_at = _utcnow()
        session.add(alias)

        session.commit()
        session.refresh(association)
        return association


def remove_from_alias(
    db_path: Path | str,
    alias_name: str,
    offering_canvas_id: int,
) -> None:
    """Remove an offering from an alias.

    Args:
        db_path: Path to the SQLite database.
        alias_name: Name of the alias.
        offering_canvas_id: Canvas course ID of the offering to remove.

    Raises:
        AliasNotFoundError: If the alias is not found.
        OfferingNotInAliasError: If the offering is not in the alias.
    """
    with get_session(db_path) as session:
        # Get the alias
        alias_stmt = select(CourseAlias).where(CourseAlias.name == alias_name)
        alias = session.exec(alias_stmt).first()
        if alias is None:
            raise AliasNotFoundError(alias_name)

        # Find the association
        assoc_stmt = select(CourseAliasOffering).where(
            CourseAliasOffering.alias_id == alias.id,
            CourseAliasOffering.offering_canvas_id == offering_canvas_id,
        )
        association = session.exec(assoc_stmt).first()
        if association is None:
            raise OfferingNotInAliasError(alias_name, offering_canvas_id)

        # Remove association
        session.delete(association)

        # Update alias timestamp
        alias.updated_at = _utcnow()
        session.add(alias)

        session.commit()


def delete_alias(
    db_path: Path | str,
    alias_name: str,
) -> None:
    """Delete an alias and all its offering associations.

    Args:
        db_path: Path to the SQLite database.
        alias_name: Name of the alias to delete.

    Raises:
        AliasNotFoundError: If the alias is not found.
    """
    from sqlalchemy import delete as sa_delete

    with get_session(db_path) as session:
        # Get the alias
        alias_stmt = select(CourseAlias).where(CourseAlias.name == alias_name)
        alias = session.exec(alias_stmt).first()
        if alias is None:
            raise AliasNotFoundError(alias_name)

        # Delete all associations first using bulk delete
        delete_stmt = sa_delete(CourseAliasOffering).where(
            CourseAliasOffering.alias_id == alias.id  # type: ignore[arg-type]
        )
        session.execute(delete_stmt)

        # Delete the alias
        session.delete(alias)
        session.commit()


def list_aliases(
    db_path: Path | str,
) -> list[dict[str, Any]]:
    """List all course aliases with their offering counts.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        List of alias dictionaries with offering counts.
    """
    with get_session(db_path) as session:
        stmt = select(CourseAlias).order_by(CourseAlias.name)
        aliases = session.exec(stmt).all()

        results: list[dict[str, Any]] = []
        for alias in aliases:
            # Count offerings in this alias
            count_stmt = select(CourseAliasOffering).where(CourseAliasOffering.alias_id == alias.id)
            offering_count = len(session.exec(count_stmt).all())

            result = alias.to_dict()
            result["offering_count"] = offering_count
            results.append(result)

        return results


def get_alias(
    db_path: Path | str,
    alias_name: str,
) -> CourseAlias | None:
    """Get an alias by name.

    Args:
        db_path: Path to the SQLite database.
        alias_name: Name of the alias.

    Returns:
        The CourseAlias or None if not found.
    """
    with get_session(db_path) as session:
        stmt = select(CourseAlias).where(CourseAlias.name == alias_name)
        return session.exec(stmt).first()


def get_alias_offerings(
    db_path: Path | str,
    alias_name: str,
) -> list[int]:
    """Get all offering Canvas IDs in an alias.

    Args:
        db_path: Path to the SQLite database.
        alias_name: Name of the alias.

    Returns:
        List of Canvas course IDs in the alias.

    Raises:
        AliasNotFoundError: If the alias is not found.
    """
    with get_session(db_path) as session:
        # Get the alias
        alias_stmt = select(CourseAlias).where(CourseAlias.name == alias_name)
        alias = session.exec(alias_stmt).first()
        if alias is None:
            raise AliasNotFoundError(alias_name)

        # Get all offering IDs
        assoc_stmt = select(CourseAliasOffering).where(CourseAliasOffering.alias_id == alias.id)
        associations = session.exec(assoc_stmt).all()

        return [assoc.offering_canvas_id for assoc in associations]


def get_offering_aliases(
    db_path: Path | str,
    offering_canvas_id: int,
) -> list[CourseAlias]:
    """Get all aliases that contain a specific offering.

    Args:
        db_path: Path to the SQLite database.
        offering_canvas_id: Canvas course ID.

    Returns:
        List of CourseAlias objects that contain this offering.
    """
    with get_session(db_path) as session:
        # Get all associations for this offering
        assoc_stmt = select(CourseAliasOffering).where(
            CourseAliasOffering.offering_canvas_id == offering_canvas_id
        )
        associations = session.exec(assoc_stmt).all()

        # Get the aliases
        aliases: list[CourseAlias] = []
        for assoc in associations:
            alias_stmt = select(CourseAlias).where(CourseAlias.id == assoc.alias_id)
            alias = session.exec(alias_stmt).first()
            if alias:
                aliases.append(alias)

        return aliases
