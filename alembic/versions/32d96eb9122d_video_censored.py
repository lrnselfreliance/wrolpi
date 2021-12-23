"""video censored

Revision ID: 32d96eb9122d
Revises: 184329ed5137
Create Date: 2021-12-23 14:03:53.677547

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '32d96eb9122d'
down_revision = '184329ed5137'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video ADD COLUMN censored BOOL DEFAULT false')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS censored')
