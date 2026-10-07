"""Add the repository table for git Repos (Collections with kind='repo').

Revision ID: 2026_10_06_1200
Revises: 2026_10_05_1200
"""
import sqlalchemy as sa
from alembic import op

import wrolpi.dates

# revision identifiers, used by Alembic.
revision = '2026_10_06_1200'
down_revision = '2026_10_05_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'repository',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=True),
        sa.Column('owner', sa.String(), nullable=True),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('default_branch', sa.String(), nullable=True),
        sa.Column('head_sha', sa.String(), nullable=True),
        sa.Column('head_date', wrolpi.dates.TZDateTime(), nullable=True),
        sa.Column('head_message', sa.Text(), nullable=True),
        sa.Column('last_fetch', wrolpi.dates.TZDateTime(), nullable=True),
        sa.Column('size', sa.BigInteger(), nullable=True),
        sa.Column('readme_path', sa.String(), nullable=True),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['collection_id'], ['collection.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('collection_id'),
        sa.UniqueConstraint('url'),
    )


def downgrade():
    op.drop_table('repository')
