"""Drop Channel.skip_download_videos.

Revision ID: 4c8da5502c8a
Revises: 8bdb48a486b9
Create Date: 2023-09-29 14:45:42.999526

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '4c8da5502c8a'
down_revision = '8bdb48a486b9'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS skip_download_videos')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS skip_download_videos TEXT[]')
