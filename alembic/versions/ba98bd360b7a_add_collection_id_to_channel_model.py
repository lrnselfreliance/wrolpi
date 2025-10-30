"""Add collection_id to Channel model

This migration:
1. Adds collection_id column to channel table
2. Creates Collection records for existing Channels
3. Links Channels to their Collections
4. Adds foreign key constraint

Revision ID: ba98bd360b7a
Revises: migrate_domains_to_collections
Create Date: 2025-11-19 21:10:56.472836

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'ba98bd360b7a'
down_revision = 'migrate_domains_to_collections'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    print("\n" + "="*60)
    print("Channel → Collection Migration")
    print("="*60 + "\n")

    # Step 1: Add collection_id column to channel table (nullable initially)
    print("Step 1: Adding collection_id column to channel table...")
    op.add_column('channel', sa.Column('collection_id', sa.Integer(), nullable=True))
    print("✓ Added collection_id column\n")

    # Step 2: Create Collection records for each Channel
    print("Step 2: Creating Collection records for existing Channels...")

    # Fetch all channels
    result = session.execute(text("""
        SELECT id, name, directory, tag_id
        FROM channel
        ORDER BY name
    """))

    channels = []
    for row in result:
        channels.append({
            'id': row[0],
            'name': row[1],
            'directory': row[2],
            'tag_id': row[3],
        })

    print(f"Found {len(channels)} Channel records to migrate")

    if channels:
        from wrolpi.collections import Collection

        for channel in channels:
            channel_id = channel['id']
            channel_name = channel['name']

            print(f"  Processing Channel {channel_id}: {channel_name}")

            # Check if Collection already exists
            existing = session.query(Collection).filter_by(
                name=channel_name,
                kind='channel'
            ).first()

            if existing:
                print(f"    Collection already exists (id={existing.id})")
                collection_id = existing.id
            else:
                # Create Collection
                collection = Collection(
                    name=channel_name,
                    kind='channel',
                    directory=channel['directory'],  # Channels always have directory
                    tag_id=channel['tag_id'],
                )
                session.add(collection)
                session.flush([collection])
                collection_id = collection.id
                print(f"    Created Collection id={collection_id}")

            # Link Channel to Collection
            session.execute(
                text("UPDATE channel SET collection_id = :collection_id WHERE id = :channel_id"),
                {'collection_id': collection_id, 'channel_id': channel_id}
            )

        session.commit()
        print(f"✓ Created Collections and linked Channels\n")
    else:
        print("No channels to migrate\n")

    # Step 3: Add foreign key constraint
    print("Step 3: Adding foreign key constraint...")
    op.create_foreign_key(
        'fk_channel_collection_id',
        'channel',
        'collection',
        ['collection_id'],
        ['id'],
        ondelete='CASCADE'
    )
    print("✓ Added foreign key constraint\n")

    print("="*60)
    print("✓ Channel → Collection Migration Complete")
    print("="*60 + "\n")

    if not DOCKERIZED:
        session.execute(text('ALTER TABLE public.channel OWNER TO wrolpi'))


def downgrade():
    # Remove foreign key constraint
    op.drop_constraint('fk_channel_collection_id', 'channel', type_='foreignkey')

    # Drop collection_id column
    op.drop_column('channel', 'collection_id')
