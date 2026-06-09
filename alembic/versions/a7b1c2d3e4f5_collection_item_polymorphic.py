"""Make collection_item polymorphic: file | zim | url items.

CollectionItem previously only referenced a FileGroup. Playlists (kind='playlist') also need to
order Zim articles (zim_id + zim_entry, mirroring TagZimEntry) and arbitrary URLs (a link the WROLPi
browser can open, e.g. a map location). This adds item_kind plus the zim/url/title columns, relaxes
file_group_id to nullable, and adds per-kind unique constraints and a CHECK that exactly one kind's
columns are populated. Existing rows default to item_kind='file'.

Revision ID: a7b1c2d3e4f5
Revises: e6f7a8b9c0d1
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b1c2d3e4f5'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None

CHECK_SQL = (
    "(item_kind = 'file' AND file_group_id IS NOT NULL AND zim_id IS NULL AND url IS NULL)"
    " OR (item_kind = 'zim' AND zim_id IS NOT NULL AND zim_entry IS NOT NULL"
    " AND file_group_id IS NULL AND url IS NULL)"
    " OR (item_kind = 'url' AND url IS NOT NULL AND file_group_id IS NULL AND zim_id IS NULL)"
)


def upgrade():
    op.add_column('collection_item',
                  sa.Column('item_kind', sa.String(), nullable=False, server_default='file'))
    op.add_column('collection_item', sa.Column('zim_id', sa.Integer(), nullable=True))
    op.add_column('collection_item', sa.Column('zim_entry', sa.Text(), nullable=True))
    op.add_column('collection_item', sa.Column('url', sa.Text(), nullable=True))
    op.add_column('collection_item', sa.Column('title', sa.Text(), nullable=True))
    # `file` is no longer the only kind, so a row need not have a FileGroup.
    op.alter_column('collection_item', 'file_group_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key('collection_item_zim_id_fkey', 'collection_item', 'zim',
                          ['zim_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_collection_zim_entry', 'collection_item',
                                ['collection_id', 'zim_id', 'zim_entry'])
    op.create_unique_constraint('uq_collection_url', 'collection_item', ['collection_id', 'url'])
    op.create_check_constraint('ck_collection_item_kind', 'collection_item', CHECK_SQL)


def downgrade():
    op.drop_constraint('ck_collection_item_kind', 'collection_item', type_='check')
    op.drop_constraint('uq_collection_url', 'collection_item', type_='unique')
    op.drop_constraint('uq_collection_zim_entry', 'collection_item', type_='unique')
    op.drop_constraint('collection_item_zim_id_fkey', 'collection_item', type_='foreignkey')
    # Restore NOT NULL (valid only if no non-file rows remain).
    op.alter_column('collection_item', 'file_group_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('collection_item', 'title')
    op.drop_column('collection_item', 'url')
    op.drop_column('collection_item', 'zim_entry')
    op.drop_column('collection_item', 'zim_id')
    op.drop_column('collection_item', 'item_kind')
