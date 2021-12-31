"""Downloader info

Revision ID: db0a1560d923
Revises: 84b6993a6091
Create Date: 2021-12-27 16:46:02.929119

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'db0a1560d923'
down_revision = '84b6993a6091'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS info_json JSONB')
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS downloader TEXT')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS info_json')
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS downloader')
