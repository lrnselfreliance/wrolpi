"""Remove duplicate Channel fields delegated to Collection

This migration removes fields from Channel that now delegate to Collection:
- name (now property: channel.name → collection.name)
- directory (now property: channel.directory → collection.directory)
- tag_id (now property: channel.tag_id → collection.tag_id)

These fields were already synced to Collection in previous migration.

Revision ID: b43f70f369d0
Revises: ba98bd360b7a
Create Date: 2025-11-19 21:48:58.488850

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b43f70f369d0'
down_revision = 'ba98bd360b7a'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    print("\n" + "="*60)
    print("Removing Duplicate Fields from Channel")
    print("="*60 + "\n")

    # Step 1: Drop foreign key constraint on tag_id
    print("Step 1: Dropping tag_id foreign key constraint...")
    op.drop_constraint('channel_tag_id_fkey', 'channel', type_='foreignkey')
    print("✓ Dropped foreign key constraint\n")

    # Step 2: Drop columns (data already in Collection)
    print("Step 2: Dropping duplicate columns...")
    op.drop_column('channel', 'name')
    print("  ✓ Dropped channel.name")
    op.drop_column('channel', 'directory')
    print("  ✓ Dropped channel.directory")
    op.drop_column('channel', 'tag_id')
    print("  ✓ Dropped channel.tag_id\n")

    print("="*60)
    print("✓ Channel Cleanup Complete")
    print("  Channels now delegate name/directory/tag to Collection")
    print("="*60 + "\n")


def downgrade():
    # Re-add the columns
    op.add_column('channel', sa.Column('name', sa.String(), nullable=True))
    op.add_column('channel', sa.Column('directory', sa.String(), nullable=True))
    op.add_column('channel', sa.Column('tag_id', sa.Integer(), nullable=True))

    # Re-add foreign key
    op.create_foreign_key('channel_tag_id_fkey', 'channel', 'tag', ['tag_id'], ['id'], ondelete='CASCADE')

    # Restore data from Collection
    bind = op.get_bind()
    bind.execute(text("""
        UPDATE channel
        SET name = collection.name,
            directory = collection.directory,
            tag_id = collection.tag_id
        FROM collection
        WHERE channel.collection_id = collection.id
    """))