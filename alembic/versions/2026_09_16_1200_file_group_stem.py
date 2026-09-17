"""Add file_group.stem for (directory, stem) grouping.

A stored stem is a cache of split_path_stem_and_suffix.  Compare joins on it.
NULL stems (and algorithm-version mismatches) are backfilled at refresh by
ensure_file_group_stems() before any compare is allowed.

The unique (directory, stem) index is intentionally omitted: duplicates are
collapsed at refresh time.  A later release can add UNIQUE after a full refresh.

Revision ID: 2026_09_16_1200
Revises: 2026_07_14_0900
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_09_16_1200'
down_revision = '2026_07_14_0900'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE file_group ADD COLUMN stem VARCHAR')
    op.execute('CREATE INDEX IF NOT EXISTS file_group_directory_stem_idx '
               'ON file_group (directory, stem)')
    op.execute('''
        CREATE TABLE IF NOT EXISTS wrolpi_kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_directory_stem_idx')
    # SQLite cannot DROP COLUMN without rebuilding the table; leave stem in place.
    op.execute('DROP TABLE IF EXISTS wrolpi_kv')
