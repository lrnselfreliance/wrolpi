"""Rename ebook table to doc and add new columns.

Revision ID: a1b2c3d4e5f6
Revises: d371333159ab
Create Date: 2026-03-15 15:30:00.000000

"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd371333159ab'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False
BATCH_SIZE = 1000


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    if not DOCKERIZED:
        bind.execute(sa.text("SET ROLE 'wrolpi'"))

    # Rename ebook table to doc.
    print("Migrating ebook -> doc...")
    op.rename_table('ebook', 'doc')

    # Rename the index.
    op.execute('ALTER INDEX IF EXISTS ebook_size_idx RENAME TO doc_size_idx')
    op.execute('ALTER INDEX IF EXISTS ebook_file_group_id_key RENAME TO doc_file_group_id_key')
    op.execute('ALTER INDEX IF EXISTS ebook_pkey RENAME TO doc_pkey')

    # Rename the sequence.
    op.execute('ALTER SEQUENCE IF EXISTS ebook_id_seq RENAME TO doc_id_seq')

    # Add new columns.
    op.add_column('doc', sa.Column('publisher', sa.String(), nullable=True))
    op.add_column('doc', sa.Column('language', sa.String(), nullable=True))
    op.add_column('doc', sa.Column('page_count', sa.Integer(), nullable=True))
    op.add_column('doc', sa.Column('subject', sa.String(), nullable=True))
    op.add_column('doc', sa.Column('description', sa.Text(), nullable=True))

    # Widen size from Integer to BigInteger.
    op.alter_column('doc', 'size', type_=sa.BigInteger(), existing_type=sa.Integer())

    # Update file_group.model: 'ebook' -> 'doc'.
    # Mark all touched file_groups as not indexed so metadata is re-extracted on next refresh.
    total = 0
    while True:
        result = bind.execute(sa.text(
            "UPDATE file_group SET model = 'doc', indexed = false"
            " WHERE id IN (SELECT id FROM file_group WHERE model = 'ebook' LIMIT :batch_size)"
        ), {'batch_size': BATCH_SIZE})
        if result.rowcount == 0:
            break
        total += result.rowcount
        print(f"  Updated {total} ebook file_groups -> doc...")
        session.commit()
    print(f"  Updated {total} ebook file_groups -> doc (done)")

    # Update file_group.model: 'pdf' -> 'doc'.
    total = 0
    while True:
        result = bind.execute(sa.text(
            "UPDATE file_group SET model = 'doc', indexed = false"
            " WHERE id IN (SELECT id FROM file_group WHERE model = 'pdf' LIMIT :batch_size)"
        ), {'batch_size': BATCH_SIZE})
        if result.rowcount == 0:
            break
        total += result.rowcount
        print(f"  Updated {total} pdf file_groups -> doc...")
        session.commit()
    print(f"  Updated {total} pdf file_groups -> doc (done)")

    # Create Doc records for existing PDFs that had no model table.
    # Metadata will be extracted when the doc_modeler re-indexes these files.
    total = 0
    while True:
        result = bind.execute(sa.text("""
            INSERT INTO doc (file_group_id)
            SELECT fg.id
            FROM file_group fg
            LEFT JOIN doc d ON d.file_group_id = fg.id
            WHERE fg.mimetype = 'application/pdf'
              AND d.id IS NULL
              AND fg.primary_path IS NOT NULL
            LIMIT :batch_size
        """), {'batch_size': BATCH_SIZE})
        if result.rowcount == 0:
            break
        total += result.rowcount
        print(f"  Created {total} new doc records for existing PDFs...")
        session.commit()
    print(f"  Created {total} new doc records for existing PDFs (done)")


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    if not DOCKERIZED:
        bind.execute(sa.text("SET ROLE 'wrolpi'"))

    # Delete doc records that were PDFs (have no ebook equivalent).
    total = 0
    while True:
        result = bind.execute(sa.text("""
            DELETE FROM doc
            WHERE id IN (
                SELECT d.id FROM doc d
                JOIN file_group fg ON fg.id = d.file_group_id
                WHERE fg.mimetype = 'application/pdf'
                LIMIT :batch_size
            )
        """), {'batch_size': BATCH_SIZE})
        if result.rowcount == 0:
            break
        total += result.rowcount
        print(f"  Deleted {total} PDF doc records...")
        session.commit()
    print(f"  Deleted {total} PDF doc records (done)")

    # Revert file_group.model and re-mark as not indexed.
    for old_model, mimetype_clause in [
        ('ebook', "mimetype LIKE 'application/epub%'"),
        ('ebook', "mimetype = 'application/x-mobipocket-ebook'"),
        ('pdf', "mimetype = 'application/pdf'"),
    ]:
        total = 0
        while True:
            result = bind.execute(sa.text(f"""
                UPDATE file_group SET model = :old_model, indexed = false
                WHERE id IN (
                    SELECT id FROM file_group
                    WHERE model = 'doc' AND {mimetype_clause}
                    LIMIT :batch_size
                )
            """), {'old_model': old_model, 'batch_size': BATCH_SIZE})
            if result.rowcount == 0:
                break
            total += result.rowcount
            print(f"  Reverted {total} file_groups -> {old_model} ({mimetype_clause})...")
            session.commit()
        print(f"  Reverted {total} file_groups -> {old_model} ({mimetype_clause}) (done)")

    # Revert size column type.
    op.alter_column('doc', 'size', type_=sa.Integer(), existing_type=sa.BigInteger())

    # Drop new columns.
    op.drop_column('doc', 'description')
    op.drop_column('doc', 'subject')
    op.drop_column('doc', 'page_count')
    op.drop_column('doc', 'language')
    op.drop_column('doc', 'publisher')

    # Rename sequences back.
    op.execute('ALTER SEQUENCE IF EXISTS doc_id_seq RENAME TO ebook_id_seq')

    # Rename indexes back.
    op.execute('ALTER INDEX IF EXISTS doc_pkey RENAME TO ebook_pkey')
    op.execute('ALTER INDEX IF EXISTS doc_file_group_id_key RENAME TO ebook_file_group_id_key')
    op.execute('ALTER INDEX IF EXISTS doc_size_idx RENAME TO ebook_size_idx')

    # Rename table back.
    op.rename_table('doc', 'ebook')
