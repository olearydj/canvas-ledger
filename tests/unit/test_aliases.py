"""Unit tests for course alias management (Phase 6)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cl.annotations.manager import (
    AliasAlreadyExistsError,
    AliasNotFoundError,
    OfferingAlreadyInAliasError,
    OfferingNotFoundError,
    OfferingNotInAliasError,
    add_to_alias,
    create_alias,
    delete_alias,
    get_alias,
    get_alias_offerings,
    get_offering_aliases,
    list_aliases,
    remove_from_alias,
)
from cl.ledger.models import Offering, Term
from cl.ledger.queries import get_alias_timeline
from cl.ledger.store import get_session, reset_engine, run_migrations


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Generator[Path]:
    """Create a temporary database with migrations applied."""
    db_path = tmp_path / "test_ledger.db"
    run_migrations(db_path, backup=False)
    yield db_path
    reset_engine()


@pytest.fixture
def seeded_db_path(temp_db_path: Path) -> Generator[Path]:
    """Create a database with test offerings seeded."""
    now = datetime.now(UTC)

    with get_session(temp_db_path) as session:
        # Create terms
        term_fall = Term(
            canvas_term_id=1,
            name="Fall 2025",
            start_date=datetime(2025, 8, 15, tzinfo=UTC),
            end_date=datetime(2025, 12, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        term_spring = Term(
            canvas_term_id=2,
            name="Spring 2026",
            start_date=datetime(2026, 1, 15, tzinfo=UTC),
            end_date=datetime(2026, 5, 15, tzinfo=UTC),
            observed_at=now,
            last_seen_at=now,
        )
        session.add(term_fall)
        session.add(term_spring)
        session.commit()
        session.refresh(term_fall)
        session.refresh(term_spring)

        # Create test offerings
        offerings = [
            Offering(
                canvas_course_id=1001,
                name="BET 3510 Fall 2025",
                code="BET 3510",
                term_id=term_fall.id,
                workflow_state="available",
                observed_at=now,
                last_seen_at=now,
            ),
            Offering(
                canvas_course_id=1002,
                name="BET 3510 Spring 2026",
                code="BET 3510",
                term_id=term_spring.id,
                workflow_state="available",
                observed_at=now,
                last_seen_at=now,
            ),
            Offering(
                canvas_course_id=1003,
                name="MNGT 4970 Special Topics: Entrepreneurship",
                code="MNGT 4970",
                term_id=term_fall.id,
                workflow_state="available",
                observed_at=now,
                last_seen_at=now,
            ),
            Offering(
                canvas_course_id=1004,
                name="Another Course",
                code="TST 101",
                term_id=term_spring.id,
                workflow_state="completed",
                observed_at=now,
                last_seen_at=now,
            ),
        ]
        for o in offerings:
            session.add(o)
        session.commit()

    yield temp_db_path


class TestCreateAlias:
    """Tests for create_alias function."""

    def test_create_alias_simple(self, seeded_db_path: Path) -> None:
        """Should create an alias without initial offerings."""
        alias = create_alias(seeded_db_path, name="BET 3510")

        assert alias.id is not None
        assert alias.name == "BET 3510"
        assert alias.description is None
        assert alias.created_at is not None
        assert alias.updated_at is not None

    def test_create_alias_with_description(self, seeded_db_path: Path) -> None:
        """Should create an alias with description."""
        alias = create_alias(
            seeded_db_path,
            name="BET 3510",
            description="Business Entrepreneurship & Technology course",
        )

        assert alias.description == "Business Entrepreneurship & Technology course"

    def test_create_alias_with_offerings(self, seeded_db_path: Path) -> None:
        """Should create an alias with initial offerings."""
        alias = create_alias(
            seeded_db_path,
            name="BET 3510",
            offering_canvas_ids=[1001, 1002],
        )

        assert alias.id is not None
        offerings = get_alias_offerings(seeded_db_path, "BET 3510")
        assert set(offerings) == {1001, 1002}

    def test_create_alias_duplicate_name(self, seeded_db_path: Path) -> None:
        """Should raise error if alias name already exists."""
        create_alias(seeded_db_path, name="BET 3510")

        with pytest.raises(AliasAlreadyExistsError) as exc_info:
            create_alias(seeded_db_path, name="BET 3510")

        assert exc_info.value.alias_name == "BET 3510"

    def test_create_alias_nonexistent_offering(self, seeded_db_path: Path) -> None:
        """Should raise error if offering doesn't exist."""
        with pytest.raises(OfferingNotFoundError) as exc_info:
            create_alias(
                seeded_db_path,
                name="BET 3510",
                offering_canvas_ids=[9999],  # Non-existent
            )

        assert exc_info.value.canvas_course_id == 9999


class TestAddToAlias:
    """Tests for add_to_alias function."""

    def test_add_to_alias_success(self, seeded_db_path: Path) -> None:
        """Should add an offering to an existing alias."""
        create_alias(seeded_db_path, name="BET 3510")

        add_to_alias(seeded_db_path, alias_name="BET 3510", offering_canvas_id=1001)

        offerings = get_alias_offerings(seeded_db_path, "BET 3510")
        assert offerings == [1001]

    def test_add_to_alias_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if alias doesn't exist."""
        with pytest.raises(AliasNotFoundError) as exc_info:
            add_to_alias(seeded_db_path, alias_name="NonExistent", offering_canvas_id=1001)

        assert exc_info.value.alias_name == "NonExistent"

    def test_add_to_alias_offering_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if offering doesn't exist."""
        create_alias(seeded_db_path, name="BET 3510")

        with pytest.raises(OfferingNotFoundError):
            add_to_alias(seeded_db_path, alias_name="BET 3510", offering_canvas_id=9999)

    def test_add_to_alias_already_in_alias(self, seeded_db_path: Path) -> None:
        """Should raise error if offering is already in alias."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001])

        with pytest.raises(OfferingAlreadyInAliasError) as exc_info:
            add_to_alias(seeded_db_path, alias_name="BET 3510", offering_canvas_id=1001)

        assert exc_info.value.alias_name == "BET 3510"
        assert exc_info.value.offering_canvas_id == 1001


class TestRemoveFromAlias:
    """Tests for remove_from_alias function."""

    def test_remove_from_alias_success(self, seeded_db_path: Path) -> None:
        """Should remove an offering from an alias."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001, 1002])

        remove_from_alias(seeded_db_path, alias_name="BET 3510", offering_canvas_id=1001)

        offerings = get_alias_offerings(seeded_db_path, "BET 3510")
        assert offerings == [1002]

    def test_remove_from_alias_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if alias doesn't exist."""
        with pytest.raises(AliasNotFoundError):
            remove_from_alias(seeded_db_path, alias_name="NonExistent", offering_canvas_id=1001)

    def test_remove_from_alias_offering_not_in_alias(self, seeded_db_path: Path) -> None:
        """Should raise error if offering is not in alias."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001])

        with pytest.raises(OfferingNotInAliasError) as exc_info:
            remove_from_alias(seeded_db_path, alias_name="BET 3510", offering_canvas_id=1002)

        assert exc_info.value.alias_name == "BET 3510"
        assert exc_info.value.offering_canvas_id == 1002


class TestDeleteAlias:
    """Tests for delete_alias function."""

    def test_delete_alias_success(self, seeded_db_path: Path) -> None:
        """Should delete an alias and its associations."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001, 1002])

        delete_alias(seeded_db_path, alias_name="BET 3510")

        alias = get_alias(seeded_db_path, "BET 3510")
        assert alias is None

    def test_delete_alias_not_found(self, seeded_db_path: Path) -> None:
        """Should raise error if alias doesn't exist."""
        with pytest.raises(AliasNotFoundError):
            delete_alias(seeded_db_path, alias_name="NonExistent")


class TestListAliases:
    """Tests for list_aliases function."""

    def test_list_aliases_empty(self, seeded_db_path: Path) -> None:
        """Should return empty list when no aliases exist."""
        aliases = list_aliases(seeded_db_path)
        assert aliases == []

    def test_list_aliases_multiple(self, seeded_db_path: Path) -> None:
        """Should return all aliases with offering counts."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001, 1002])
        create_alias(seeded_db_path, name="Entrepreneurship", offering_canvas_ids=[1003])
        create_alias(seeded_db_path, name="Empty Alias")

        aliases = list_aliases(seeded_db_path)

        assert len(aliases) == 3

        # Should be sorted by name
        assert aliases[0]["name"] == "BET 3510"
        assert aliases[0]["offering_count"] == 2

        assert aliases[1]["name"] == "Empty Alias"
        assert aliases[1]["offering_count"] == 0

        assert aliases[2]["name"] == "Entrepreneurship"
        assert aliases[2]["offering_count"] == 1


class TestGetAlias:
    """Tests for get_alias function."""

    def test_get_alias_exists(self, seeded_db_path: Path) -> None:
        """Should return alias when it exists."""
        create_alias(seeded_db_path, name="BET 3510", description="Test description")

        alias = get_alias(seeded_db_path, "BET 3510")

        assert alias is not None
        assert alias.name == "BET 3510"
        assert alias.description == "Test description"

    def test_get_alias_not_found(self, seeded_db_path: Path) -> None:
        """Should return None when alias doesn't exist."""
        alias = get_alias(seeded_db_path, "NonExistent")
        assert alias is None


class TestGetOfferingAliases:
    """Tests for get_offering_aliases function."""

    def test_get_offering_aliases_single(self, seeded_db_path: Path) -> None:
        """Should return aliases containing an offering."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001])

        aliases = get_offering_aliases(seeded_db_path, 1001)

        assert len(aliases) == 1
        assert aliases[0].name == "BET 3510"

    def test_get_offering_aliases_multiple(self, seeded_db_path: Path) -> None:
        """Should return multiple aliases if offering is in several."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001])
        create_alias(seeded_db_path, name="Fall Courses", offering_canvas_ids=[1001, 1003])

        aliases = get_offering_aliases(seeded_db_path, 1001)

        assert len(aliases) == 2
        names = {a.name for a in aliases}
        assert names == {"BET 3510", "Fall Courses"}

    def test_get_offering_aliases_none(self, seeded_db_path: Path) -> None:
        """Should return empty list if offering is not in any alias."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001])

        aliases = get_offering_aliases(seeded_db_path, 1002)  # Not in any alias

        assert aliases == []


class TestGetAliasTimeline:
    """Tests for get_alias_timeline query function."""

    def test_get_alias_timeline_success(self, seeded_db_path: Path) -> None:
        """Should return timeline for alias offerings."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001, 1002])

        timeline = get_alias_timeline(seeded_db_path, "BET 3510")

        assert timeline is not None
        assert timeline.alias_name == "BET 3510"
        assert len(timeline.offerings) == 2

        # Should be sorted by term (most recent first)
        # Spring 2026 should come before Fall 2025
        offering_names = [o.offering_name for o in timeline.offerings]
        assert "BET 3510 Spring 2026" in offering_names
        assert "BET 3510 Fall 2025" in offering_names

    def test_get_alias_timeline_not_found(self, seeded_db_path: Path) -> None:
        """Should return None when alias doesn't exist."""
        timeline = get_alias_timeline(seeded_db_path, "NonExistent")
        assert timeline is None

    def test_get_alias_timeline_empty(self, seeded_db_path: Path) -> None:
        """Should return empty offerings list for alias with no offerings."""
        create_alias(seeded_db_path, name="Empty Alias")

        timeline = get_alias_timeline(seeded_db_path, "Empty Alias")

        assert timeline is not None
        assert timeline.alias_name == "Empty Alias"
        assert timeline.offerings == []


class TestAliasModels:
    """Tests for alias model to_dict methods."""

    def test_course_alias_to_dict(self, seeded_db_path: Path) -> None:
        """CourseAlias.to_dict should include all fields."""
        alias = create_alias(
            seeded_db_path,
            name="BET 3510",
            description="Test description",
        )

        data = alias.to_dict()

        assert data["id"] == alias.id
        assert data["annotation_type"] == "course_alias"
        assert data["name"] == "BET 3510"
        assert data["description"] == "Test description"
        assert "created_at" in data
        assert "updated_at" in data

    def test_alias_timeline_to_dict(self, seeded_db_path: Path) -> None:
        """AliasTimeline.to_dict should include all fields."""
        create_alias(seeded_db_path, name="BET 3510", offering_canvas_ids=[1001, 1002])

        timeline = get_alias_timeline(seeded_db_path, "BET 3510")
        data = timeline.to_dict()

        assert data["alias_name"] == "BET 3510"
        assert data["total_offerings"] == 2
        assert len(data["offerings"]) == 2

        # Each offering should have expected fields
        off_data = data["offerings"][0]
        assert "canvas_course_id" in off_data
        assert "offering_name" in off_data
        assert "term_name" in off_data
