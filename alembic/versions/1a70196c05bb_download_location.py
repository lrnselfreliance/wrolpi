"""Download location

Revision ID: 1a70196c05bb
Revises: d8fcdb7773c0
Create Date: 2022-05-02 12:01:51.210070

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '1a70196c05bb'
down_revision = 'd8fcdb7773c0'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS location TEXT')
    session.execute('ALTER TABLE download ADD COLUMN IF NOT EXISTS error TEXT')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS location')
    session.execute('ALTER TABLE download DROP COLUMN IF EXISTS error')
