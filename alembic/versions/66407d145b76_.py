"""Create collection table for domain collections

Revision ID: 66407d145b76
Revises: 4f03b9548f6e
Create Date: 2025-10-26 10:57:16.462524

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = '66407d145b76'
down_revision = '4f03b9548f6e'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Step 1: Create new collection table (keeping channel table separate for now)
    op.create_table(
        'collection',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('directory', sa.Text(), nullable=True),
        sa.Column('tag_id', sa.Integer(), nullable=True),
        sa.Column('created_date', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('item_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_size', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name='collection_tag_id_fkey'),
        sa.UniqueConstraint('directory', name='uq_collection_directory')
    )

    # Create indexes for collection
    op.create_index('idx_collection_kind', 'collection', ['kind'], unique=False)
    op.create_index('idx_collection_item_count', 'collection', ['item_count'], unique=False)
    op.create_index('idx_collection_total_size', 'collection', ['total_size'], unique=False)

    # Step 2: Create collection_item junction table
    op.create_table(
        'collection_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.Column('file_group_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('added_date', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['collection_id'], ['collection.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_group_id'], ['file_group.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('collection_id', 'file_group_id', name='uq_collection_file_group')
    )

    # Create indexes for collection_item
    op.create_index('idx_collection_item_collection_id', 'collection_item', ['collection_id'], unique=False)
    op.create_index('idx_collection_item_file_group_id', 'collection_item', ['file_group_id'], unique=False)
    op.create_index('idx_collection_item_position', 'collection_item', ['position'], unique=False)
    op.create_index('idx_collection_item_collection_position', 'collection_item', ['collection_id', 'position'], unique=False)

    # Ensure table owner in non-docker environments
    if not DOCKERIZED:
        session.execute(sa.text('ALTER TABLE public.collection OWNER TO wrolpi'))
        session.execute(sa.text('ALTER TABLE public.collection_item OWNER TO wrolpi'))


def downgrade():
    # Drop collection_item table and its indexes
    op.drop_index('idx_collection_item_collection_position', table_name='collection_item')
    op.drop_index('idx_collection_item_position', table_name='collection_item')
    op.drop_index('idx_collection_item_file_group_id', table_name='collection_item')
    op.drop_index('idx_collection_item_collection_id', table_name='collection_item')
    op.drop_table('collection_item')

    # Drop collection table and its indexes
    op.drop_index('idx_collection_total_size', table_name='collection')
    op.drop_index('idx_collection_item_count', table_name='collection')
    op.drop_index('idx_collection_kind', table_name='collection')
    op.drop_table('collection')
