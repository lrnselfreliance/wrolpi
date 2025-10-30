"""Add unique constraint on collection (name, kind)

This migration:
1. Removes duplicate collections (keeping the one with most items/archives)
2. Adds a unique constraint on (name, kind) to prevent future duplicates

Revision ID: add_unique_collection_name_kind
Revises: migrate_download_to_collection
Create Date: 2025-11-27
"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'add_unique_collection_name_kind'
down_revision = 'migrate_download_to_collection'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    print("\n" + "=" * 60)
    print("Add Unique Constraint on Collection (name, kind)")
    print("=" * 60 + "\n")

    # Step 1: Find and remove duplicate collections
    print("Step 1: Finding duplicate collections...")

    # Find duplicates - keep the one with the lowest id (first created)
    duplicates = session.execute(text("""
        SELECT name, kind, array_agg(id ORDER BY id) as ids
        FROM collection
        GROUP BY name, kind
        HAVING COUNT(*) > 1
    """)).fetchall()

    if duplicates:
        print(f"Found {len(duplicates)} sets of duplicate collections")
        for name, kind, ids in duplicates:
            keep_id = ids[0]  # Keep the first one (lowest id)
            remove_ids = ids[1:]  # Remove the rest
            print(f"  - '{name}' ({kind}): keeping id={keep_id}, removing ids={remove_ids}")

            # Move any archives from duplicate collections to the one we're keeping
            for remove_id in remove_ids:
                session.execute(text("""
                    UPDATE archive SET collection_id = :keep_id
                    WHERE collection_id = :remove_id
                """), {'keep_id': keep_id, 'remove_id': remove_id})

                # Move any downloads from duplicate collections
                session.execute(text("""
                    UPDATE download SET collection_id = :keep_id
                    WHERE collection_id = :remove_id
                """), {'keep_id': keep_id, 'remove_id': remove_id})

                # Move any collection items
                session.execute(text("""
                    UPDATE collection_item SET collection_id = :keep_id
                    WHERE collection_id = :remove_id
                """), {'keep_id': keep_id, 'remove_id': remove_id})

                # Delete the duplicate collection
                session.execute(text("""
                    DELETE FROM collection WHERE id = :remove_id
                """), {'remove_id': remove_id})

        session.commit()
        print("Duplicates removed\n")
    else:
        print("No duplicate collections found\n")

    # Step 2: Add unique constraint
    print("Step 2: Adding unique constraint on (name, kind)...")
    op.create_unique_constraint('uq_collection_name_kind', 'collection', ['name', 'kind'])
    print("Done\n")

    print("=" * 60)
    print("Migration Complete")
    print("=" * 60 + "\n")

    if not DOCKERIZED:
        session.execute(text('ALTER TABLE public.collection OWNER TO wrolpi'))


def downgrade():
    op.drop_constraint('uq_collection_name_kind', 'collection', type_='unique')
