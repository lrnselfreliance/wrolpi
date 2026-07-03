"""file_group_textsearch_abc

Add the `textsearch_abc` generated tsvector column to `file_group`.  It indexes only a_text (title),
b_text (author), and c_text (description) — excluding d_text (captions/document body), which is ~90% of all
text data.  Searches default to this much smaller column; the existing `textsearch` column remains for
opt-in "deep" search.

Adding a STORED generated column rewrites the table; expect a few minutes on large libraries.

Revision ID: e5f7a9c1d3b6
Revises: d4e6f8a0c2b5
Create Date: 2026-07-03

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e5f7a9c1d3b6'
down_revision = 'd4e6f8a0c2b5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text('''
        ALTER TABLE file_group
        ADD COLUMN textsearch_abc tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, COALESCE(a_text, '')), 'A'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(b_text, '')), 'B'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(c_text, '')), 'C'::"char")
        ) STORED
    '''))
    conn.execute(sa.text(
        'CREATE INDEX IF NOT EXISTS file_group_textsearch_abc_idx ON file_group USING GIN(textsearch_abc)'))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('DROP INDEX IF EXISTS file_group_textsearch_abc_idx'))
    conn.execute(sa.text('ALTER TABLE file_group DROP COLUMN IF EXISTS textsearch_abc'))
