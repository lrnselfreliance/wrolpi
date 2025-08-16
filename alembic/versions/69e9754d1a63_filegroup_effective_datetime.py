"""FileGroup.effective_datetime

Revision ID: 69e9754d1a63
Revises: f7229a67e333
Create Date: 2025-08-16 10:28:42.661108

"""
import os
from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '69e9754d1a63'
down_revision = 'f7229a67e333'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    op.execute('ALTER TABLE file_group ADD COLUMN IF NOT EXISTS effective_datetime TIMESTAMPTZ')

    # Populating effective_datetime for existing rows
    op.execute("""
               UPDATE file_group
               SET effective_datetime = COALESCE(published_datetime, download_datetime)
               WHERE published_datetime IS NOT NULL
                  OR download_datetime IS NOT NULL;
               """)

    op.execute('CREATE INDEX IF NOT EXISTS file_group_effective_datetime_idx ON file_group(effective_datetime)')


def downgrade():
    op.execute('DROP INDEX IF EXISTS file_group_effective_datetime_idx')
    op.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS effective_datetime')
