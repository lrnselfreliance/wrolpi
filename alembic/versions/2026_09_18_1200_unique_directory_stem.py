"""Unique (directory, stem) on file_group.

713 added the stem column and a non-unique index.  This release collapses any
remaining duplicate (directory, stem) rows (moving tags and collection
membership onto the winner) and makes the index UNIQUE.

Revision ID: 2026_09_18_1200
Revises: 2026_09_16_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_09_18_1200'
down_revision = '2026_09_16_1200'
branch_labels = None
depends_on = None


def upgrade():
    from wrolpi.files.lib import backfill_null_file_group_stems, dedupe_file_groups_by_directory_stem

    backfill_null_file_group_stems()
    dedupe_file_groups_by_directory_stem()
    op.execute('DROP INDEX IF EXISTS file_group_directory_stem_idx')
    op.execute('CREATE UNIQUE INDEX file_group_directory_stem_idx ON file_group (directory, stem)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_directory_stem_idx')
    op.execute('CREATE INDEX IF NOT EXISTS file_group_directory_stem_idx ON file_group (directory, stem)')
