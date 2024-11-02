"""Create Download.destination column.

Revision ID: 170d1be52bc7
Revises: 9ec4c765ef8d
Create Date: 2024-11-02 11:16:15.297850

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '170d1be52bc7'
down_revision = '9ec4c765ef8d'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS destination TEXT')
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS tag_names TEXT[]')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS tag_names')
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS destination')
