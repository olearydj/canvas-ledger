"""Add Section, Person, Enrollment tables for deep ingestion.

Revision ID: 004
Revises: 003
Create Date: 2026-01-06

Phase 3 tables enable deep ingestion of offerings:
- Section: subdivisions of an offering
- Person: users encountered through enrollments
- Enrollment: detailed enrollment records with grade data
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create section table
    op.create_table(
        "section",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_section_id", sa.Integer(), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sis_section_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["offering_id"], ["offering.id"]),
        sa.UniqueConstraint("canvas_section_id"),
    )
    op.create_index(
        op.f("ix_section_canvas_section_id"),
        "section",
        ["canvas_section_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_section_offering_id"),
        "section",
        ["offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_section_sis_section_id"),
        "section",
        ["sis_section_id"],
        unique=False,
    )

    # Create person table
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sortable_name", sa.String(), nullable=True),
        sa.Column("sis_user_id", sa.String(), nullable=True),
        sa.Column("login_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canvas_user_id"),
    )
    op.create_index(
        op.f("ix_person_canvas_user_id"),
        "person",
        ["canvas_user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_person_sis_user_id"),
        "person",
        ["sis_user_id"],
        unique=False,
    )

    # Create enrollment table
    op.create_table(
        "enrollment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canvas_enrollment_id", sa.Integer(), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("enrollment_state", sa.String(), nullable=False),
        sa.Column("current_grade", sa.String(), nullable=True),
        sa.Column("current_score", sa.Float(), nullable=True),
        sa.Column("final_grade", sa.String(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["offering_id"], ["offering.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.UniqueConstraint("canvas_enrollment_id"),
    )
    op.create_index(
        op.f("ix_enrollment_canvas_enrollment_id"),
        "enrollment",
        ["canvas_enrollment_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_enrollment_offering_id"),
        "enrollment",
        ["offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_enrollment_section_id"),
        "enrollment",
        ["section_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_enrollment_person_id"),
        "enrollment",
        ["person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("enrollment")
    op.drop_table("person")
    op.drop_table("section")
