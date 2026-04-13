"""Force EPUB re-extraction after spine-ordering fix.

A previous version of `extract_epub` used `book.get_items_of_type(ITEM_DOCUMENT)`
to enumerate sections, which returns manifest order (not reading-spine order) and
can include non-spine documents like EPUB 3 `nav.xhtml`. The viewer resolves
deep-links via `spine.get(n)`, so any `doc_section.ordinal` written by the old
code can land users on the wrong chapter.

The fix iterates `book.spine` directly; this migration flips `indexed = FALSE`
on every EPUB file group so the regular refresh pipeline re-extracts them with
correct spine-indexed ordinals. PDFs are untouched — their per-page ordinals
were always correct.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-13

"""
from alembic import op

revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        UPDATE file_group
        SET indexed = FALSE
        WHERE mimetype LIKE 'application/epub%'
    ''')


def downgrade():
    # Symmetric with the parent migration's downgrade safeguard: if we re-apply
    # downgrade, leave file groups marked indexed so a refresh doesn't try to
    # repopulate doc_section rows that may have been dropped by the parent.
    op.execute('''
        UPDATE file_group
        SET indexed = TRUE
        WHERE mimetype LIKE 'application/epub%'
    ''')
