"""make_filegroup_directory_not_null

Revision ID: 26c5a62ec683
Revises: af4527503bdf
Create Date: 2025-12-23 20:47:11.549264

This migration makes the `directory` column NOT NULL after the previous migration
has populated it for all existing FileGroups.
"""
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '26c5a62ec683'
down_revision = 'af4527503bdf'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Safety check: ensure no NULL directory values remain
    result = session.execute(sa.text(
        "SELECT COUNT(*) FROM file_group WHERE directory IS NULL"
    ))
    null_count = result.scalar()
    if null_count > 0:
        # Fill any remaining NULL values (shouldn't happen if previous migration ran)
        print(f"Warning: Found {null_count} FileGroups with NULL directory, filling from primary_path...")
        session.execute(sa.text("""
            UPDATE file_group
            SET directory = regexp_replace(primary_path, '/[^/]+$', '')
            WHERE directory IS NULL AND primary_path IS NOT NULL
        """))
        session.commit()

    # Make the column NOT NULL
    op.alter_column('file_group', 'directory', nullable=False)

    # Create index on directory column for efficient directory lookups
    op.create_index('file_group_directory_idx', 'file_group', ['directory'])

    if not DOCKERIZED:
        session.execute(sa.text('ALTER TABLE public.file_group OWNER TO wrolpi'))


def downgrade():
    # Drop the index
    op.drop_index('file_group_directory_idx', 'file_group')
    # Make the column nullable again
    op.alter_column('file_group', 'directory', nullable=True)
