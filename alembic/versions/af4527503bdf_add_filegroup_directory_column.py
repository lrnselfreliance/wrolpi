"""add_filegroup_directory_column

Revision ID: af4527503bdf
Revises: 577e414f1bc4
Create Date: 2025-12-23 19:35:18.776018

This migration:
1. Adds `directory` column to file_group (stores parent directory of primary_path)
2. Converts paths in `files` JSON from absolute to relative (filename only)
3. Converts paths in `data` JSON from absolute to relative (filename only)

After this migration:
- directory: /media/wrolpi/videos/channel1 (absolute)
- primary_path: /media/wrolpi/videos/channel1/video.mp4 (absolute, unchanged for now)
- files: [{path: "video.mp4", ...}] (relative filenames)
- data: {poster_path: "video.jpg", ...} (relative filenames)

Processing is done in batches to handle large databases (hundreds of thousands of FileGroups)
on memory-constrained devices like Raspberry Pi.
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

import wrolpi.media_path

# revision identifiers, used by Alembic.
revision = 'af4527503bdf'
down_revision = '577e414f1bc4'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False

# Batch size for processing - balances memory usage vs. migration speed
BATCH_SIZE = 1000


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Add the directory column (nullable initially)
    # Index is created in the next migration (26c5a62ec683) AFTER data is populated for efficiency.
    op.add_column('file_group', sa.Column('directory', wrolpi.media_path.MediaPathType(), nullable=True))

    # Phase 1: Populate directory from existing primary_path (batched)
    # Uses regexp_replace to remove the filename (everything after the last /).
    print("Phase 1: Populating directory column...")
    total_updated = 0
    while True:
        result = session.execute(sa.text("""
            UPDATE file_group
            SET directory = regexp_replace(primary_path, '/[^/]+$', '')
            WHERE id IN (
                SELECT id FROM file_group
                WHERE directory IS NULL
                  AND primary_path IS NOT NULL
                LIMIT :batch_size
            )
        """), {'batch_size': BATCH_SIZE})
        session.commit()
        if result.rowcount == 0:
            break
        total_updated += result.rowcount
        print(f"  Processed {total_updated} directories...")
    print(f"Phase 1 complete: {total_updated} directories populated.")

    # Phase 2: Convert files JSON paths from absolute to relative (batched)
    # Only processes rows where at least one path is still absolute (starts with /)
    print("Phase 2: Converting files JSON to relative paths...")
    total_updated = 0
    while True:
        result = session.execute(sa.text("""
            UPDATE file_group
            SET files = (
                SELECT jsonb_agg(
                    jsonb_set(
                        elem,
                        '{path}',
                        to_jsonb(regexp_replace(elem->>'path', '.+/', ''))
                    )
                )
                FROM jsonb_array_elements(files::jsonb) AS elem
            )
            WHERE id IN (
                SELECT id FROM file_group
                WHERE files IS NOT NULL
                  AND jsonb_array_length(files::jsonb) > 0
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(files::jsonb) AS elem
                      WHERE elem->>'path' LIKE '/%'
                  )
                LIMIT :batch_size
            )
        """), {'batch_size': BATCH_SIZE})
        session.commit()
        if result.rowcount == 0:
            break
        total_updated += result.rowcount
        print(f"  Converted {total_updated} files arrays...")
    print(f"Phase 2 complete: {total_updated} files arrays converted.")

    # Phase 3: Convert data JSON paths from absolute to relative (batched)
    # Handle known path fields: video_path, info_json_path, poster_path, ebook_path, cover_path, screenshot_path
    # Only processes rows where data contains at least one absolute path
    print("Phase 3: Converting data JSON to relative paths...")
    total_updated = 0
    while True:
        result = session.execute(sa.text("""
            UPDATE file_group
            SET data = (
                SELECT COALESCE(
                    jsonb_object_agg(
                        key,
                        CASE
                            -- Handle path fields that are strings starting with /
                            -- Use ::jsonb cast instead of to_jsonb() since value::text already has JSON quotes
                            WHEN key IN ('video_path', 'info_json_path', 'poster_path', 'ebook_path', 'cover_path', 'screenshot_path',
                                         'readability_json_path', 'readability_path', 'readability_txt_path', 'singlefile_path')
                                 AND jsonb_typeof(value) = 'string'
                                 AND value::text LIKE '"/%%'
                            THEN regexp_replace(value::text, '^".+/', '"')::jsonb

                            -- Handle caption_paths which is an array of strings
                            WHEN key = 'caption_paths' AND jsonb_typeof(value) = 'array'
                            THEN (
                                SELECT jsonb_agg(
                                    CASE
                                        WHEN jsonb_typeof(elem) = 'string' AND elem::text LIKE '"/%%'
                                        THEN regexp_replace(elem::text, '^".+/', '"')::jsonb
                                        ELSE elem
                                    END
                                )
                                FROM jsonb_array_elements(value) AS elem
                            )

                            -- Keep other values unchanged
                            ELSE value
                        END
                    ),
                    '{}'::jsonb
                )
                FROM jsonb_each(data::jsonb)
            )
            WHERE id IN (
                SELECT id FROM file_group
                WHERE data IS NOT NULL
                  AND data::text != 'null'
                  AND data::text != '{}'
                  AND (
                      -- Check if any known path field contains an absolute path
                      data->>'video_path' LIKE '/%'
                      OR data->>'info_json_path' LIKE '/%'
                      OR data->>'poster_path' LIKE '/%'
                      OR data->>'ebook_path' LIKE '/%'
                      OR data->>'cover_path' LIKE '/%'
                      OR data->>'screenshot_path' LIKE '/%'
                      OR data->>'readability_json_path' LIKE '/%'
                      OR data->>'readability_path' LIKE '/%'
                      OR data->>'readability_txt_path' LIKE '/%'
                      OR data->>'singlefile_path' LIKE '/%'
                      OR EXISTS (
                          SELECT 1 FROM jsonb_array_elements_text(
                              CASE WHEN data->>'caption_paths' IS NOT NULL THEN (data->'caption_paths')::jsonb ELSE '[]'::jsonb END
                          ) AS elem
                          WHERE elem LIKE '/%'
                      )
                  )
                LIMIT :batch_size
            )
        """), {'batch_size': BATCH_SIZE})
        session.commit()
        if result.rowcount == 0:
            break
        total_updated += result.rowcount
        print(f"  Converted {total_updated} data objects...")
    print(f"Phase 3 complete: {total_updated} data objects converted.")

    print("Migration complete!")

    if not DOCKERIZED:
        session.execute(sa.text('ALTER TABLE public.file_group OWNER TO wrolpi'))


def downgrade():
    # Note: Downgrade does not restore absolute paths in files/data columns.
    # This would require knowing the original directory for each record.
    # Index is dropped in the previous downgrade (26c5a62ec683).
    op.drop_column('file_group', 'directory')
