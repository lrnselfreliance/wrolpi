"""file_group_suffix

Add the `suffix` column to the `file_group` table.  This stores the lowercased suffix of the primary file
(e.g. ".bin") so searches can filter by file type using an index, rather than relying on full-text tokens.

The `from_paths` model method keeps this column up to date going forward (via `split_path_stem_and_suffix`).
Existing rows are backfilled here with the final extension of the primary_path; any multi-part suffixes
(e.g. ".info.json") are corrected on the next file refresh.

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


def upgrade():
    op.add_column('file_group', sa.Column('suffix', sa.String(), nullable=True))
    op.create_index('ix_file_group_suffix', 'file_group', ['suffix'])
    # Backfill existing rows with the lowercased final extension of the primary_path.
    op.execute(r"""
        UPDATE file_group
        SET suffix = lower(substring(primary_path FROM '\.[^./]+$'))
        WHERE primary_path ~ '\.[^./]+$'
    """)


def downgrade():
    op.drop_index('ix_file_group_suffix', table_name='file_group')
    op.drop_column('file_group', 'suffix')
