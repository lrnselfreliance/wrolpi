"""file_group_suffix

Add the `suffix` column to the `file_group` table.  This stores the lowercased suffix of the primary file
(e.g. ".bin") so searches can filter by file type using an index, rather than relying on full-text tokens.

`suffix` is populated at ingest time alongside `mimetype` (wrolpi.files.lib._upsert_files and
FileGroup.from_paths).  Existing rows are backfilled here using the same `split_path_stem_and_suffix` logic so
special multi-part suffixes like ".info.json" are stored correctly (not a naive ".json").

Revision ID: d4e6f8a0c2b5
Revises: c3d5f7a9b1e2
Create Date: 2026-07-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e6f8a0c2b5'
down_revision = 'c3d5f7a9b1e2'
branch_labels = None
depends_on = None

# Backfill in batches to bound memory on low-RAM devices (e.g. Raspberry Pi).
BATCH_SIZE = 5000


def upgrade():
    op.add_column('file_group', sa.Column('suffix', sa.String(), nullable=True))
    op.create_index('ix_file_group_suffix', 'file_group', ['suffix'])

    # Backfill existing rows using the same suffix logic used at ingest time so the stored value matches what
    # future refreshes would produce (including WROLPi special suffixes like ".info.json").
    from wrolpi.files.lib import split_path_stem_and_suffix
    conn = op.get_bind()
    last_id = 0
    while True:
        rows = conn.execute(
            sa.text('SELECT id, primary_path FROM file_group WHERE id > :last_id ORDER BY id LIMIT :limit'),
            {'last_id': last_id, 'limit': BATCH_SIZE},
        ).fetchall()
        if not rows:
            break

        ids, suffixes = [], []
        for row_id, primary_path in rows:
            suffix = (split_path_stem_and_suffix(primary_path)[1] or '').lower() or None
            if suffix:
                ids.append(row_id)
                suffixes.append(suffix)

        if ids:
            conn.execute(
                sa.text('''
                    UPDATE file_group AS fg
                    SET suffix = v.suffix
                    FROM (SELECT unnest(cast(:ids AS integer[])) AS id,
                                 unnest(cast(:suffixes AS text[])) AS suffix) AS v
                    WHERE fg.id = v.id
                '''),
                {'ids': ids, 'suffixes': suffixes},
            )

        last_id = rows[-1][0]


def downgrade():
    op.drop_index('ix_file_group_suffix', table_name='file_group')
    op.drop_column('file_group', 'suffix')
