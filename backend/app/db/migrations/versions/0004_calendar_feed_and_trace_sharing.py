"""calendar feed and trace sharing

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("calendar_token_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("calendar_created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("users_calendar_token_hash_key", "users", ["calendar_token_hash"])
    op.add_column(
        "message_feedback",
        sa.Column("share_trace", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("message_feedback", "share_trace")
    op.drop_constraint("users_calendar_token_hash_key", "users", type_="unique")
    op.drop_column("users", "calendar_created_at")
    op.drop_column("users", "calendar_token_hash")
