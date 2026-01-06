"""Canvas API client for canvas-ledger.

Provides a read-only interface to the Canvas LMS API.
Uses the canvasapi library for core functionality.

All API calls are GET requests - cl never mutates Canvas state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from canvasapi import Canvas
from canvasapi.exceptions import CanvasException, InvalidAccessToken, ResourceDoesNotExist

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from canvasapi.enrollment_term import EnrollmentTerm


class CanvasClientError(Exception):
    """Base exception for Canvas client errors."""

    pass


class CanvasAuthenticationError(CanvasClientError):
    """Raised when Canvas authentication fails."""

    pass


class CanvasNotFoundError(CanvasClientError):
    """Raised when a requested resource is not found."""

    pass


@dataclass
class CourseData:
    """Normalized course data from Canvas API."""

    canvas_course_id: int
    name: str
    code: str | None
    workflow_state: str
    term_id: int | None
    enrollments: list[EnrollmentData]


@dataclass
class EnrollmentData:
    """Normalized enrollment data from Canvas API."""

    canvas_enrollment_id: int
    role: str
    enrollment_state: str
    course_id: int


@dataclass
class TermData:
    """Normalized term data from Canvas API."""

    canvas_term_id: int
    name: str
    start_date: datetime | None
    end_date: datetime | None


@dataclass
class SectionData:
    """Normalized section data from Canvas API."""

    canvas_section_id: int
    course_id: int
    name: str
    sis_section_id: str | None


@dataclass
class CourseEnrollmentData:
    """Normalized enrollment data for deep ingestion.

    Contains full enrollment details including user info and grades.
    """

    canvas_enrollment_id: int
    course_id: int
    course_section_id: int | None
    user_id: int
    role: str
    enrollment_state: str
    # User info (included to avoid separate API calls)
    user_name: str
    user_sortable_name: str | None
    user_sis_id: str | None
    user_login_id: str | None
    # Grade data (may be null)
    current_grade: str | None
    current_score: float | None
    final_grade: str | None
    final_score: float | None


@dataclass
class UserData:
    """Normalized user data from Canvas API."""

    canvas_user_id: int
    name: str
    sortable_name: str | None
    sis_user_id: str | None
    login_id: str | None


class CanvasClient:
    """Client for interacting with Canvas API.

    This client is read-only - it never modifies Canvas state.
    """

    def __init__(self, base_url: str, api_token: str) -> None:
        """Initialize Canvas client.

        Args:
            base_url: Canvas instance base URL (e.g., "https://canvas.instructure.com").
            api_token: Canvas API access token.
        """
        self._base_url = base_url.rstrip("/")
        self._canvas = Canvas(self._base_url, api_token)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse a datetime string from Canvas API response."""
        if not value:
            return None
        try:
            # Canvas returns ISO 8601 format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _fetch_my_enrollments(self) -> dict[int, list[EnrollmentData]]:
        """Fetch all enrollments for the current user.

        Returns:
            Dict mapping course_id to list of EnrollmentData for that course.
        """
        user = self._canvas.get_current_user()
        enrollments_by_course: dict[int, list[EnrollmentData]] = {}

        # Request all enrollment states, not just active
        all_states = ["active", "invited", "creation_pending", "rejected", "completed", "inactive"]
        for enrollment in user.get_enrollments(state=all_states):
            course_id = int(enrollment.course_id)
            enrollment_data = EnrollmentData(
                canvas_enrollment_id=int(enrollment.id),
                role=str(getattr(enrollment, "role", "unknown")),
                enrollment_state=str(getattr(enrollment, "enrollment_state", "unknown")),
                course_id=course_id,
            )

            if course_id not in enrollments_by_course:
                enrollments_by_course[course_id] = []
            enrollments_by_course[course_id].append(enrollment_data)

        return enrollments_by_course

    def list_my_courses(self) -> list[CourseData]:
        """List all courses visible to the authenticated user.

        Returns all courses regardless of the user's role (teacher, TA, student, etc.).
        Includes enrollment information for the user in each course.

        Returns:
            List of CourseData objects with normalized course information.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            # First, fetch all enrollments with proper IDs
            enrollments_by_course = self._fetch_my_enrollments()

            # Request courses with term info
            courses = self._canvas.get_current_user().get_courses(
                include=["term"],
            )

            result: list[CourseData] = []
            skipped_count = 0
            for course in courses:
                # Skip courses with restricted access (no details available)
                if getattr(course, "access_restricted_by_date", False):
                    skipped_count += 1
                    logger.warning("Skipping course %s: access restricted by date", course.id)
                    continue

                # Extract term ID if available
                term_id: int | None = None
                term = getattr(course, "term", None)
                if term:
                    if isinstance(term, dict):
                        term_id = term.get("id")
                    else:
                        term_id = getattr(term, "id", None)

                # Look up enrollments for this course
                course_id = int(course.id)
                enrollments = enrollments_by_course.get(course_id, [])

                result.append(
                    CourseData(
                        canvas_course_id=int(course.id),
                        name=str(course.name),
                        code=getattr(course, "course_code", None),
                        workflow_state=str(getattr(course, "workflow_state", "available")),
                        term_id=int(term_id) if term_id else None,
                        enrollments=enrollments,
                    )
                )

            if skipped_count > 0:
                logger.info("Skipped %d course(s) due to date-restricted access", skipped_count)

            return result

        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e

    def get_term(self, term_id: int) -> TermData | None:
        """Get term details by ID.

        Args:
            term_id: Canvas term (enrollment_term) ID.

        Returns:
            TermData object or None if term not found.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            # Get the root account to access enrollment terms
            # Note: This requires appropriate permissions
            account = self._canvas.get_account("self")
            term: EnrollmentTerm = account.get_enrollment_term(term_id)

            return TermData(
                canvas_term_id=int(term.id),
                name=str(term.name),
                start_date=self._parse_datetime(getattr(term, "start_at", None)),
                end_date=self._parse_datetime(getattr(term, "end_at", None)),
            )

        except ResourceDoesNotExist:
            return None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            # If we can't access terms via account API, try getting term from course
            # This is a fallback for users without account-level access
            raise CanvasClientError(
                f"Failed to retrieve term {term_id}. "
                "You may not have permission to access enrollment terms directly."
            ) from e

    def get_term_from_course(self, course_id: int) -> TermData | None:
        """Get term details from a course.

        This is a fallback method when direct term access is not available.
        Fetches the course and extracts its term information.

        Args:
            course_id: Canvas course ID.

        Returns:
            TermData object or None if course has no term.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            course = self._canvas.get_course(course_id, include=["term"])
            term = getattr(course, "term", None)

            if not term:
                return None

            if isinstance(term, dict):
                return TermData(
                    canvas_term_id=int(term["id"]),
                    name=str(term.get("name", "Unknown Term")),
                    start_date=self._parse_datetime(term.get("start_at")),
                    end_date=self._parse_datetime(term.get("end_at")),
                )
            else:
                return TermData(
                    canvas_term_id=int(term.id),
                    name=str(getattr(term, "name", "Unknown Term")),
                    start_date=self._parse_datetime(getattr(term, "start_at", None)),
                    end_date=self._parse_datetime(getattr(term, "end_at", None)),
                )

        except ResourceDoesNotExist:
            raise CanvasNotFoundError(f"Course {course_id} not found.") from None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e

    def list_sections(self, course_id: int) -> list[SectionData]:
        """List all sections for a course.

        Args:
            course_id: Canvas course ID.

        Returns:
            List of SectionData objects.

        Raises:
            CanvasNotFoundError: If the course is not found.
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            course = self._canvas.get_course(course_id)
            sections = course.get_sections()

            result: list[SectionData] = []
            for section in sections:
                result.append(
                    SectionData(
                        canvas_section_id=int(section.id),
                        course_id=int(course_id),
                        name=str(section.name),
                        sis_section_id=getattr(section, "sis_section_id", None),
                    )
                )

            return result

        except ResourceDoesNotExist:
            raise CanvasNotFoundError(f"Course {course_id} not found.") from None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e

    def list_enrollments(self, course_id: int) -> list[CourseEnrollmentData]:
        """List all enrollments for a course.

        Fetches all enrollments (all roles, all states) for a course,
        including user information and grade data.

        Args:
            course_id: Canvas course ID.

        Returns:
            List of CourseEnrollmentData objects.

        Raises:
            CanvasNotFoundError: If the course is not found.
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            course = self._canvas.get_course(course_id)

            # Request all enrollment states and include user info
            all_states = [
                "active",
                "invited",
                "creation_pending",
                "rejected",
                "completed",
                "inactive",
                "deleted",
            ]
            enrollments = course.get_enrollments(
                state=all_states,
                include=["user"],
            )

            result: list[CourseEnrollmentData] = []
            for enrollment in enrollments:
                # Extract user info from the enrollment object
                user = getattr(enrollment, "user", {}) or {}
                if isinstance(user, dict):
                    user_name = user.get("name", "Unknown")
                    user_sortable_name = user.get("sortable_name")
                    user_sis_id = user.get("sis_user_id")
                    user_login_id = user.get("login_id")
                else:
                    user_name = getattr(user, "name", "Unknown")
                    user_sortable_name = getattr(user, "sortable_name", None)
                    user_sis_id = getattr(user, "sis_user_id", None)
                    user_login_id = getattr(user, "login_id", None)

                # Extract grade data (may be in nested 'grades' dict)
                grades = getattr(enrollment, "grades", {}) or {}
                current_grade = grades.get("current_grade") if isinstance(grades, dict) else None
                current_score = grades.get("current_score") if isinstance(grades, dict) else None
                final_grade = grades.get("final_grade") if isinstance(grades, dict) else None
                final_score = grades.get("final_score") if isinstance(grades, dict) else None

                result.append(
                    CourseEnrollmentData(
                        canvas_enrollment_id=int(enrollment.id),
                        course_id=int(course_id),
                        course_section_id=getattr(enrollment, "course_section_id", None),
                        user_id=int(enrollment.user_id),
                        role=str(getattr(enrollment, "role", "unknown")),
                        enrollment_state=str(getattr(enrollment, "enrollment_state", "unknown")),
                        user_name=str(user_name),
                        user_sortable_name=user_sortable_name,
                        user_sis_id=user_sis_id,
                        user_login_id=user_login_id,
                        current_grade=current_grade,
                        current_score=float(current_score) if current_score else None,
                        final_grade=final_grade,
                        final_score=float(final_score) if final_score else None,
                    )
                )

            return result

        except ResourceDoesNotExist:
            raise CanvasNotFoundError(f"Course {course_id} not found.") from None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e

    def get_user(self, user_id: int) -> UserData | None:
        """Get user details by ID.

        Args:
            user_id: Canvas user ID.

        Returns:
            UserData object or None if user not found.

        Raises:
            CanvasAuthenticationError: If the API token is invalid.
            CanvasClientError: For other API errors.
        """
        try:
            user = self._canvas.get_user(user_id)

            return UserData(
                canvas_user_id=int(user.id),
                name=str(user.name),
                sortable_name=getattr(user, "sortable_name", None),
                sis_user_id=getattr(user, "sis_user_id", None),
                login_id=getattr(user, "login_id", None),
            )

        except ResourceDoesNotExist:
            return None
        except InvalidAccessToken as e:
            raise CanvasAuthenticationError(
                "Canvas API token is invalid or expired. Please update your token configuration."
            ) from e
        except CanvasException as e:
            raise CanvasClientError(f"Canvas API error: {e}") from e


def create_client(base_url: str, api_token: str) -> CanvasClient:
    """Factory function to create a Canvas client.

    Args:
        base_url: Canvas instance base URL.
        api_token: Canvas API access token.

    Returns:
        Configured CanvasClient instance.
    """
    return CanvasClient(base_url, api_token)
