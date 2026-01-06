"""006: Course alias tables.

Adds tables for course aliasing (Phase 6):
- course_alias: Groups related offerings under a common name
- course_alias_offering: Many-to-many association between aliases and offerings

This supports canonical query Q7: course identity continuity across
renumbering, special topics variations, and local naming conventions.

Revision ID: 006
Revises: 005
Create Date: 2026-01-06
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create course_alias table
    op.create_table(
        "course_alias",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "name",
            sa.String(),
            nullable=False,
            unique=True,
            comment="Alias name (e.g., 'BET 3510', 'Intro to Programming')",
        ),
        sa.Column(
            "description",
            sa.String(),
            nullable=True,
            comment="Optional description explaining this alias grouping",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the alias was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the alias was last updated",
        ),
    )

    # Index for efficient name lookups
    op.create_index(
        "ix_course_alias_name",
        "course_alias",
        ["name"],
    )

    # Create course_alias_offering association table
    # Note: Unique constraint included in create_table to avoid SQLite ALTER limitations
    op.create_table(
        "course_alias_offering",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "alias_id",
            sa.Integer(),
            sa.ForeignKey("course_alias.id", ondelete="CASCADE"),
            nullable=False,
            comment="Reference to the alias",
        ),
        sa.Column(
            "offering_canvas_id",
            sa.Integer(),
            nullable=False,
            comment="Canvas course ID of the associated offering",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When this association was created",
        ),
        # Unique constraint: an offering can only be in an alias once
        sa.UniqueConstraint("alias_id", "offering_canvas_id", name="uq_course_alias_offering"),
    )

    # Indexes for efficient queries
    # Query pattern: "which offerings are in this alias?"
    op.create_index(
        "ix_course_alias_offering_alias_id",
        "course_alias_offering",
        ["alias_id"],
    )
    # Query pattern: "which aliases does this offering belong to?"
    op.create_index(
        "ix_course_alias_offering_canvas_id",
        "course_alias_offering",
        ["offering_canvas_id"],
    )


def downgrade() -> None:
    # Note: unique constraint is dropped automatically when table is dropped
    op.drop_index("ix_course_alias_offering_canvas_id", table_name="course_alias_offering")
    op.drop_index("ix_course_alias_offering_alias_id", table_name="course_alias_offering")
    op.drop_table("course_alias_offering")
    op.drop_index("ix_course_alias_name", table_name="course_alias")
    op.drop_table("course_alias")
