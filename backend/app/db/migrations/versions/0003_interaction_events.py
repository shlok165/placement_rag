"""interaction events

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_interaction_events_user_kind", "interaction_events", ["user_id", "kind", "created_at"]
    )
    op.create_index("ix_interaction_events_job_id", "interaction_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_interaction_events_job_id", table_name="interaction_events")
    op.drop_index("ix_interaction_events_user_kind", table_name="interaction_events")
    op.drop_table("interaction_events")
