"""005: History tracking schema.

Adds change_log table for tracking entity changes across ingestion runs.

Design decision (T065): Using Option C - Change Log Table approach.
- Single table tracks all entity changes
- Stores: entity type, canvas ID, field, old/new values, ingest run reference
- Enables rich drift queries without modifying existing tables
- Non-intrusive to existing schema

Revision ID: 005
Revises: 004
Create Date: 2026-01-06
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create change_log table
    op.create_table(
        "change_log",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        # Entity reference
        sa.Column(
            "entity_type",
            sa.String(),
            nullable=False,
            comment="Entity type: offering, enrollment, person, section, user_enrollment, term",
        ),
        sa.Column(
            "entity_canvas_id",
            sa.Integer(),
            nullable=False,
            comment="Canvas ID of the entity (course_id, user_id, enrollment_id, etc.)",
        ),
        # Change details
        sa.Column("field_name", sa.String(), nullable=False, comment="Name of the changed field"),
        sa.Column(
            "old_value",
            sa.String(),
            nullable=True,
            comment="Previous value (null for new entities)",
        ),
        sa.Column(
            "new_value", sa.String(), nullable=True, comment="New value (null for deletions)"
        ),
        # Tracking
        sa.Column(
            "ingest_run_id",
            sa.Integer(),
            sa.ForeignKey("ingest_run.id"),
            nullable=False,
            comment="Ingest run that detected this change",
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the change was observed",
        ),
    )

    # Indexes for efficient queries
    # Query pattern: "what changed for this entity?"
    op.create_index(
        "ix_change_log_entity",
        "change_log",
        ["entity_type", "entity_canvas_id"],
    )
    # Query pattern: "what changed in this ingest run?"
    op.create_index(
        "ix_change_log_ingest_run",
        "change_log",
        ["ingest_run_id"],
    )
    # Query pattern: "when did this change happen?"
    op.create_index(
        "ix_change_log_observed_at",
        "change_log",
        ["observed_at"],
    )
    # Query pattern: "drift for a specific entity type" (e.g., all enrollment changes)
    op.create_index(
        "ix_change_log_entity_type_observed",
        "change_log",
        ["entity_type", "observed_at"],
    )

    # Add drift_count to ingest_run for quick access to drift summary
    op.add_column(
        "ingest_run",
        sa.Column("drift_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_index("ix_change_log_entity_type_observed", table_name="change_log")
    op.drop_index("ix_change_log_observed_at", table_name="change_log")
    op.drop_index("ix_change_log_ingest_run", table_name="change_log")
    op.drop_index("ix_change_log_entity", table_name="change_log")
    op.drop_table("change_log")
    op.drop_column("ingest_run", "drift_count")
