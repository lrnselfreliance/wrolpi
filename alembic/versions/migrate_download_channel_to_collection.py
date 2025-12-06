"""Migrate Download.channel_id to Download.collection_id

This migration:
1. Adds collection_id column to download table
2. Migrates existing channel_id references to collection_id via Channel.collection_id
3. Drops channel_id column and foreign key

Revision ID: migrate_download_to_collection
Revises: b43f70f369d0
Create Date: 2025-11-27
"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'migrate_download_to_collection'
down_revision = 'b43f70f369d0'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    print("\n" + "=" * 60)
    print("Download channel_id -> collection_id Migration")
    print("=" * 60 + "\n")

    # Step 1: Add collection_id column (nullable initially)
    print("Step 1: Adding collection_id column to download table...")
    op.add_column('download', sa.Column('collection_id', sa.Integer(), nullable=True))
    print("Done\n")

    # Step 2: Migrate data - lookup collection_id through channel
    print("Step 2: Migrating channel_id to collection_id...")
    result = session.execute(text("""
        UPDATE download
        SET collection_id = channel.collection_id
        FROM channel
        WHERE download.channel_id = channel.id
          AND download.channel_id IS NOT NULL
    """))
    print(f"Updated {result.rowcount} download records\n")

    # Step 3: Add foreign key constraint
    print("Step 3: Adding foreign key constraint...")
    op.create_foreign_key(
        'fk_download_collection_id',
        'download',
        'collection',
        ['collection_id'],
        ['id'],
        ondelete='SET NULL'
    )
    print("Done\n")

    # Step 4: Create index for performance
    print("Step 4: Creating index on collection_id...")
    op.create_index('idx_download_collection_id', 'download', ['collection_id'])
    print("Done\n")

    # Step 5: Drop old channel_id foreign key and column
    print("Step 5: Dropping channel_id column...")
    op.drop_constraint('download_channel_id_fkey', 'download', type_='foreignkey')
    op.drop_column('download', 'channel_id')
    print("Done\n")

    # Step 6: Fix the update_channel_minimum_frequency trigger function
    # It was referencing channel_id which no longer exists
    print("Step 6: Updating update_channel_minimum_frequency trigger function...")
    op.execute("""
        CREATE OR REPLACE FUNCTION update_channel_minimum_frequency()
            RETURNS TRIGGER AS
        $$
        DECLARE
            v_channel_id INTEGER;
        BEGIN
            -- Handle INSERT and UPDATE: use NEW record
            IF (TG_OP = 'DELETE') THEN
                -- For DELETE, we need to find the channel from OLD record
                IF OLD.collection_id IS NOT NULL THEN
                    SELECT id INTO v_channel_id FROM channel WHERE collection_id = OLD.collection_id;
                    IF v_channel_id IS NOT NULL THEN
                        UPDATE channel
                        SET minimum_frequency = (SELECT MIN(frequency) FROM download WHERE collection_id = OLD.collection_id)
                        WHERE id = v_channel_id;
                    END IF;
                END IF;
                RETURN OLD;
            ELSE
                -- For INSERT and UPDATE, use NEW record
                IF NEW.collection_id IS NOT NULL THEN
                    SELECT id INTO v_channel_id FROM channel WHERE collection_id = NEW.collection_id;
                    IF v_channel_id IS NOT NULL THEN
                        UPDATE channel
                        SET minimum_frequency = (SELECT MIN(frequency) FROM download WHERE collection_id = NEW.collection_id)
                        WHERE id = v_channel_id;
                    END IF;
                END IF;
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)
    print("Done\n")

    print("=" * 60)
    print("Migration Complete")
    print("=" * 60 + "\n")

    if not DOCKERIZED:
        session.execute(text('ALTER TABLE public.download OWNER TO wrolpi'))


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Restore the old trigger function that uses channel_id
    op.execute("""
        CREATE OR REPLACE FUNCTION update_channel_minimum_frequency()
            RETURNS TRIGGER AS
        $$
        BEGIN
            UPDATE channel
            SET minimum_frequency = (SELECT MIN(frequency) FROM download WHERE channel_id = NEW.channel_id)
            WHERE id = NEW.channel_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Add back channel_id column
    op.add_column('download', sa.Column('channel_id', sa.Integer(), nullable=True))

    # Migrate collection_id back to channel_id
    session.execute(text("""
        UPDATE download
        SET channel_id = channel.id
        FROM channel
        WHERE download.collection_id = channel.collection_id
          AND download.collection_id IS NOT NULL
    """))

    # Add foreign key constraint
    op.create_foreign_key(
        'download_channel_id_fkey',
        'download',
        'channel',
        ['channel_id'],
        ['id']
    )

    # Drop collection_id
    op.drop_index('idx_download_collection_id', 'download')
    op.drop_constraint('fk_download_collection_id', 'download', type_='foreignkey')
    op.drop_column('download', 'collection_id')
