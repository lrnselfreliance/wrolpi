"""Create doc_section table for per-chapter/per-page full-text search.

Enables deep-linking from search results into a specific EPUB chapter or PDF page,
and fixes a latent completeness bug in full-text search where FileGroup.d_text is
truncated to ~100KB (so only the first ~30 pages of a big PDF were searchable).

Existing EPUB and PDF FileGroups are marked `indexed = FALSE` so that the regular
refresh pipeline re-runs their extractors and populates doc_section rows. No one-off
script is required. Note: the next refresh on a populated library will be heavier
than usual while every EPUB and PDF is re-extracted.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-13

"""
from alembic import op

revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE doc_section (
            id BIGSERIAL PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES doc(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            label TEXT,
            content TEXT,
            tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english'::regconfig, COALESCE(content, ''))) STORED
        )
    ''')
    op.execute('CREATE INDEX doc_section_doc_id_idx ON doc_section (doc_id, ordinal)')
    op.execute('CREATE INDEX doc_section_tsv_idx ON doc_section USING GIN (tsv)')

    # Force a re-index of all EPUB and PDF file groups so the refresh pipeline
    # populates the new doc_section table.
    op.execute('''
        UPDATE file_group
        SET indexed = FALSE
        WHERE mimetype LIKE 'application/epub%'
           OR mimetype = 'application/pdf'
    ''')


def downgrade():
    op.execute('DROP TABLE IF EXISTS doc_section')
