"""download_last_download_attempt

Add the `last_download_attempt` column to the `download` table.  This records the last time a Download was
dispatched (whether the attempt succeeds or fails) and is used to enforce per-domain and global daily download
limits.  An index supports the "attempted since local midnight" count query.

Revision ID: c3d5f7a9b1e2
Revises: b2e4f6a8c1d3
Create Date: 2026-06-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d5f7a9b1e2'
down_revision = 'b2e4f6a8c1d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('download', sa.Column('last_download_attempt', sa.DateTime(timezone=True), nullable=True))
    op.create_index('idx_download_last_download_attempt', 'download', ['last_download_attempt'])


def downgrade():
    op.drop_index('idx_download_last_download_attempt', table_name='download')
    op.drop_column('download', 'last_download_attempt')
