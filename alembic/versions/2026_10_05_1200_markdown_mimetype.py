"""Retag existing markdown file groups as text/markdown.

A refresh skips a group whose files have not changed, so markdown indexed before text/markdown
existed would keep the type libmagic gave it (text/plain, or a programming language when the file
holds code) and the indexer that type chose.  Marking the rows unindexed lets apply_indexers
re-index them with TextIndexer.  SQLite's LIKE is case-insensitive for ASCII, so `.MD` matches.

Revision ID: 2026_10_05_1200
Revises: 2026_09_28_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_10_05_1200'
down_revision = '2026_09_28_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE file_group SET mimetype = 'text/markdown', "indexed" = 0
        WHERE (primary_path LIKE '%.md' OR primary_path LIKE '%.markdown')
          AND mimetype LIKE 'text/%'
          AND mimetype != 'text/markdown'
    """)


def downgrade():
    # The original types are not recorded; text/plain is what libmagic reports for most markdown.
    op.execute("""UPDATE file_group SET mimetype = 'text/plain', "indexed" = 0 WHERE mimetype = 'text/markdown'""")
