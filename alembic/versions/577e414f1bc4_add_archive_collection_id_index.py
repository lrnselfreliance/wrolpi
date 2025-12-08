"""add_archive_collection_id_index

Revision ID: 577e414f1bc4
Revises: f38cfe4b5cb2
Create Date: 2025-12-07 17:25:27.809843

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '577e414f1bc4'
down_revision = 'f38cfe4b5cb2'
branch_labels = None
depends_on = None


def upgrade():
    # Add index on archive.collection_id to speed up GROUP BY queries
    # and per-collection lookups. This index was missing and causing
    # full table scans on the archive table (115k+ rows).
    op.create_index('idx_archive_collection_id', 'archive', ['collection_id'])


def downgrade():
    op.drop_index('idx_archive_collection_id', table_name='archive')
