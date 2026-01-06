"""Unit tests for Canvas client module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from cl.canvas.client import (
    CanvasAuthenticationError,
    CanvasClient,
    CanvasClientError,
    CourseData,
    EnrollmentData,
    TermData,
)


class MockCourse:
    """Mock Canvas course object."""

    def __init__(
        self,
        course_id: int,
        name: str,
        code: str | None = None,
        term: dict | None = None,
        enrollments: list | None = None,
        workflow_state: str = "available",
    ):
        self.id = course_id
        self.name = name
        self.course_code = code
        self.term = term
        self.enrollments = enrollments or []
        self.workflow_state = workflow_state


class MockEnrollmentTerm:
    """Mock Canvas enrollment term object."""

    def __init__(
        self,
        term_id: int,
        name: str,
        start_at: str | None = None,
        end_at: str | None = None,
    ):
        self.id = term_id
        self.name = name
        self.start_at = start_at
        self.end_at = end_at


class MockEnrollment:
    """Mock Canvas enrollment object."""

    def __init__(
        self,
        enrollment_id: int,
        course_id: int,
        role: str = "StudentEnrollment",
        enrollment_state: str = "active",
    ):
        self.id = enrollment_id
        self.course_id = course_id
        self.role = role
        self.enrollment_state = enrollment_state


class MockUser:
    """Mock Canvas user object."""

    def __init__(self, courses: list, enrollments: list | None = None):
        self._courses = courses
        self._enrollments = enrollments or []

    def get_courses(self, include: list | None = None):  # noqa: ARG002
        """Return mock courses."""
        return iter(self._courses)

    def get_enrollments(self, state: list | None = None):  # noqa: ARG002
        """Return mock enrollments."""
        return iter(self._enrollments)


class MockAccount:
    """Mock Canvas account object."""

    def __init__(self, terms: dict | None = None):
        self._terms = terms or {}

    def get_enrollment_term(self, term_id: int):
        """Return mock term or raise if not found."""
        from canvasapi.exceptions import ResourceDoesNotExist

        if term_id not in self._terms:
            raise ResourceDoesNotExist("Term not found")
        return self._terms[term_id]


class TestCanvasClient:
    """Tests for CanvasClient class."""

    @pytest.fixture
    def mock_canvas(self):
        """Create a mock Canvas instance."""
        with patch("cl.canvas.client.Canvas") as mock:
            yield mock

    def test_init_strips_trailing_slash(self, mock_canvas):  # noqa: ARG002
        """Client should strip trailing slash from base URL."""
        client = CanvasClient("https://canvas.example.edu/", "token")
        assert client._base_url == "https://canvas.example.edu"

    def test_parse_datetime_iso_format(self, mock_canvas):  # noqa: ARG002
        """Should parse ISO 8601 datetime strings."""
        client = CanvasClient("https://canvas.example.edu", "token")

        result = client._parse_datetime("2024-01-15T10:30:00Z")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_datetime_none(self, mock_canvas):  # noqa: ARG002
        """Should return None for None input."""
        client = CanvasClient("https://canvas.example.edu", "token")

        result = client._parse_datetime(None)

        assert result is None

    def test_parse_datetime_empty_string(self, mock_canvas):  # noqa: ARG002
        """Should return None for empty string."""
        client = CanvasClient("https://canvas.example.edu", "token")

        result = client._parse_datetime("")

        assert result is None


class TestListMyCourses:
    """Tests for list_my_courses method."""

    @pytest.fixture
    def mock_canvas(self):
        """Create a mock Canvas instance."""
        with patch("cl.canvas.client.Canvas") as mock:
            yield mock

    def test_list_my_courses_empty(self, mock_canvas):
        """Should return empty list when no courses."""
        mock_user = MockUser(courses=[], enrollments=[])
        mock_canvas.return_value.get_current_user.return_value = mock_user

        client = CanvasClient("https://canvas.example.edu", "token")
        courses = client.list_my_courses()

        assert courses == []

    def test_list_my_courses_with_courses(self, mock_canvas):
        """Should return normalized course data."""
        mock_courses = [
            MockCourse(
                course_id=123,
                name="Test Course",
                code="TST101",
                term={"id": 1, "name": "Fall 2024"},
            ),
            MockCourse(
                course_id=789,
                name="Another Course",
                code="ANT201",
                workflow_state="completed",
            ),
        ]
        mock_enrollments = [
            MockEnrollment(enrollment_id=456, course_id=123, role="teacher", enrollment_state="active"),
        ]
        mock_user = MockUser(courses=mock_courses, enrollments=mock_enrollments)
        mock_canvas.return_value.get_current_user.return_value = mock_user

        client = CanvasClient("https://canvas.example.edu", "token")
        courses = client.list_my_courses()

        assert len(courses) == 2

        # First course
        assert courses[0].canvas_course_id == 123
        assert courses[0].name == "Test Course"
        assert courses[0].code == "TST101"
        assert courses[0].term_id == 1
        assert courses[0].workflow_state == "available"
        assert len(courses[0].enrollments) == 1
        assert courses[0].enrollments[0].role == "teacher"

        # Second course (no enrollment)
        assert courses[1].canvas_course_id == 789
        assert courses[1].name == "Another Course"
        assert courses[1].workflow_state == "completed"
        assert courses[1].term_id is None

    def test_list_my_courses_handles_multiple_enrollments(self, mock_canvas):
        """Should handle multiple enrollments per course."""
        mock_courses = [
            MockCourse(
                course_id=123,
                name="Test Course",
            ),
        ]
        mock_enrollments = [
            MockEnrollment(enrollment_id=100, course_id=123, role="StudentEnrollment", enrollment_state="active"),
            MockEnrollment(enrollment_id=101, course_id=123, role="TeacherEnrollment", enrollment_state="invited"),
        ]
        mock_user = MockUser(courses=mock_courses, enrollments=mock_enrollments)
        mock_canvas.return_value.get_current_user.return_value = mock_user

        client = CanvasClient("https://canvas.example.edu", "token")
        courses = client.list_my_courses()

        enrollments = courses[0].enrollments
        assert len(enrollments) == 2
        assert enrollments[0].canvas_enrollment_id == 100
        assert enrollments[0].role == "StudentEnrollment"
        assert enrollments[1].canvas_enrollment_id == 101
        assert enrollments[1].role == "TeacherEnrollment"

    def test_list_my_courses_auth_error(self, mock_canvas):
        """Should raise CanvasAuthenticationError on invalid token."""
        from canvasapi.exceptions import InvalidAccessToken

        mock_canvas.return_value.get_current_user.side_effect = InvalidAccessToken("Invalid token")

        client = CanvasClient("https://canvas.example.edu", "bad-token")

        with pytest.raises(CanvasAuthenticationError) as exc_info:
            client.list_my_courses()

        assert "invalid or expired" in str(exc_info.value).lower()

    def test_list_my_courses_api_error(self, mock_canvas):
        """Should raise CanvasClientError on API errors."""
        from canvasapi.exceptions import CanvasException

        mock_canvas.return_value.get_current_user.side_effect = CanvasException("API Error")

        client = CanvasClient("https://canvas.example.edu", "token")

        with pytest.raises(CanvasClientError) as exc_info:
            client.list_my_courses()

        assert "API error" in str(exc_info.value)


class TestGetTerm:
    """Tests for get_term method."""

    @pytest.fixture
    def mock_canvas(self):
        """Create a mock Canvas instance."""
        with patch("cl.canvas.client.Canvas") as mock:
            yield mock

    def test_get_term_success(self, mock_canvas):
        """Should return term data for valid term ID."""
        mock_term = MockEnrollmentTerm(
            term_id=1,
            name="Fall 2024",
            start_at="2024-08-15T00:00:00Z",
            end_at="2024-12-15T23:59:59Z",
        )
        mock_account = MockAccount(terms={1: mock_term})
        mock_canvas.return_value.get_account.return_value = mock_account

        client = CanvasClient("https://canvas.example.edu", "token")
        term = client.get_term(1)

        assert term is not None
        assert term.canvas_term_id == 1
        assert term.name == "Fall 2024"
        assert term.start_date is not None
        assert term.end_date is not None

    def test_get_term_not_found(self, mock_canvas):
        """Should return None for nonexistent term."""
        mock_account = MockAccount(terms={})
        mock_canvas.return_value.get_account.return_value = mock_account

        client = CanvasClient("https://canvas.example.edu", "token")
        term = client.get_term(999)

        assert term is None


class TestGetTermFromCourse:
    """Tests for get_term_from_course method."""

    @pytest.fixture
    def mock_canvas(self):
        """Create a mock Canvas instance."""
        with patch("cl.canvas.client.Canvas") as mock:
            yield mock

    def test_get_term_from_course_with_dict_term(self, mock_canvas):
        """Should extract term from course with dict term."""
        mock_course = MockCourse(
            course_id=123,
            name="Test Course",
            term={
                "id": 1,
                "name": "Fall 2024",
                "start_at": "2024-08-15T00:00:00Z",
                "end_at": "2024-12-15T23:59:59Z",
            },
        )
        mock_canvas.return_value.get_course.return_value = mock_course

        client = CanvasClient("https://canvas.example.edu", "token")
        term = client.get_term_from_course(123)

        assert term is not None
        assert term.canvas_term_id == 1
        assert term.name == "Fall 2024"

    def test_get_term_from_course_no_term(self, mock_canvas):
        """Should return None when course has no term."""
        mock_course = MockCourse(course_id=123, name="Test Course", term=None)
        mock_canvas.return_value.get_course.return_value = mock_course

        client = CanvasClient("https://canvas.example.edu", "token")
        term = client.get_term_from_course(123)

        assert term is None

    def test_get_term_from_course_not_found(self, mock_canvas):
        """Should raise CanvasNotFoundError for nonexistent course."""
        from canvasapi.exceptions import ResourceDoesNotExist

        from cl.canvas.client import CanvasNotFoundError

        mock_canvas.return_value.get_course.side_effect = ResourceDoesNotExist("Course not found")

        client = CanvasClient("https://canvas.example.edu", "token")

        with pytest.raises(CanvasNotFoundError):
            client.get_term_from_course(999)


class TestDataClasses:
    """Tests for data classes."""

    def test_course_data_fields(self):
        """CourseData should have expected fields."""
        enrollment = EnrollmentData(
            canvas_enrollment_id=1,
            role="teacher",
            enrollment_state="active",
            course_id=123,
        )
        course = CourseData(
            canvas_course_id=123,
            name="Test Course",
            code="TST101",
            workflow_state="available",
            term_id=1,
            enrollments=[enrollment],
        )

        assert course.canvas_course_id == 123
        assert course.name == "Test Course"
        assert course.code == "TST101"
        assert course.workflow_state == "available"
        assert course.term_id == 1
        assert len(course.enrollments) == 1

    def test_term_data_fields(self):
        """TermData should have expected fields."""
        term = TermData(
            canvas_term_id=1,
            name="Fall 2024",
            start_date=datetime(2024, 8, 15, tzinfo=UTC),
            end_date=datetime(2024, 12, 15, tzinfo=UTC),
        )

        assert term.canvas_term_id == 1
        assert term.name == "Fall 2024"
        assert term.start_date is not None
        assert term.end_date is not None

    def test_enrollment_data_fields(self):
        """EnrollmentData should have expected fields."""
        enrollment = EnrollmentData(
            canvas_enrollment_id=456,
            role="StudentEnrollment",
            enrollment_state="active",
            course_id=123,
        )

        assert enrollment.canvas_enrollment_id == 456
        assert enrollment.role == "StudentEnrollment"
        assert enrollment.enrollment_state == "active"
        assert enrollment.course_id == 123
