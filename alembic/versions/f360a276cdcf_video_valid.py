"""Video.valid.

Revision ID: f360a276cdcf
Revises: 8bdb48a486b9
Create Date: 2023-08-07 22:49:37.001794

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'f360a276cdcf'
down_revision = '8bdb48a486b9'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE video ADD COLUMN validated BOOLEAN DEFAULT FALSE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS validated')
