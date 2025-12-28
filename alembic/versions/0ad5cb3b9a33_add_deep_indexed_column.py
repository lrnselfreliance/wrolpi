"""add_deep_indexed_column

Adds deep_indexed column to file_group table for two-phase indexing:
- indexed=True means surface indexed (filename searchable, file visible)
- deep_indexed=True means content extracted (full text search available)

Existing indexed files are marked as deep_indexed=True since they've already
been fully processed by the old single-phase indexing.

Revision ID: 0ad5cb3b9a33
Revises: 26c5a62ec683
Create Date: 2025-12-26 20:33:37.657206

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = '0ad5cb3b9a33'
down_revision = '26c5a62ec683'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Add the column as nullable first
    op.add_column('file_group', sa.Column('deep_indexed', sa.Boolean(), nullable=True))

    # Set default for all existing rows - existing indexed files are already deep indexed
    # (they went through the old single-phase indexing which extracted content)
    session.execute(sa.text("UPDATE file_group SET deep_indexed = indexed WHERE indexed IS NOT NULL"))
    session.execute(sa.text("UPDATE file_group SET deep_indexed = FALSE WHERE deep_indexed IS NULL"))

    # Add NOT NULL constraint after populating
    op.alter_column('file_group', 'deep_indexed', nullable=False, server_default=sa.text('FALSE'))

    # Create index for query performance on deep indexing queries
    op.create_index('ix_file_group_deep_indexed', 'file_group', ['deep_indexed'])

    # Composite index for common query pattern: find surface-indexed but not deep-indexed
    op.create_index('ix_file_group_indexed_deep', 'file_group', ['indexed', 'deep_indexed'])


def downgrade():
    op.drop_index('ix_file_group_indexed_deep')
    op.drop_index('ix_file_group_deep_indexed')
    op.drop_column('file_group', 'deep_indexed')
