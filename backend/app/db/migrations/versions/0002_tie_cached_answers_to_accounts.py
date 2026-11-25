"""tie cached answers to accounts

Revision ID: 0002
Revises: 0001
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('llm_cache', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_llm_cache_user_id'), 'llm_cache', ['user_id'], unique=False)
    op.create_foreign_key('llm_cache_user_id_fkey', 'llm_cache', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('llm_cache_user_id_fkey', 'llm_cache', type_='foreignkey')
    op.drop_index(op.f('ix_llm_cache_user_id'), table_name='llm_cache')
    op.drop_column('llm_cache', 'user_id')
