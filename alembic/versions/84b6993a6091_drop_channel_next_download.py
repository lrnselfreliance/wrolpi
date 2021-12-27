"""Drop channel next_download

Revision ID: 84b6993a6091
Revises: 8df411232c17
Create Date: 2021-12-27 16:42:32.099796

"""
import os
from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = '84b6993a6091'
down_revision = '8df411232c17'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS next_download')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS next_download DATE')
