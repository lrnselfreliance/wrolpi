"""Maintain collection.item_count/total_size for Domain Collections with triggers.

Listing Domain Collections summed file_group.size through an archive join on every request,
one random page read per archive.  The new triggers keep the summary columns current
(as the channel triggers already do for Channels); this migration installs them and
backfills existing Domain Collections.

Revision ID: 2026_09_27_1200
Revises: 2026_09_20_1200
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026_09_27_1200'
down_revision = '2026_09_20_1200'
branch_labels = None
depends_on = None

TRIGGERS = (
    'archive_insert_collection_summary',
    'archive_delete_collection_summary',
    'archive_update_collection_summary',
    'file_group_size_collection_summary',
)


def upgrade():
    from wrolpi.schema_ddl import install_raw_ddl

    # Idempotent: only the new triggers are created.
    install_raw_ddl(op.get_bind())

    op.execute('''
        UPDATE collection SET
            item_count = (SELECT COUNT(*) FROM archive WHERE collection_id = collection.id),
            total_size = (SELECT COALESCE(SUM(fg.size), 0) FROM archive a
                          LEFT JOIN file_group fg ON a.file_group_id = fg.id
                          WHERE a.collection_id = collection.id)
        WHERE kind = 'domain'
    ''')


def downgrade():
    for name in TRIGGERS:
        op.execute(f'DROP TRIGGER IF EXISTS {name}')
