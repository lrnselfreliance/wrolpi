"""Channel.download_missing_data

Revision ID: f7229a67e333
Revises: dc6637ced17b
Create Date: 2025-02-19 14:02:57.952791

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'f7229a67e333'
down_revision = 'dc6637ced17b'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS download_missing_data BOOLEAN DEFAULT True')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS download_missing_data')
