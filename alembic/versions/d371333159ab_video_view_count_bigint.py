"""Video view_count bigint.

Revision ID: d371333159ab
Revises: b2b9700f5048
Create Date: 2026-02-08

This migration changes the view_count column from INTEGER to BIGINT
to accommodate YouTube videos with view counts exceeding 2,147,483,647.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd371333159ab'
down_revision = 'b2b9700f5048'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('video', 'view_count',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger())


def downgrade():
    op.alter_column('video', 'view_count',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer())
