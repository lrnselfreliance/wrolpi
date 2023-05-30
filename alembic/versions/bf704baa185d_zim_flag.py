"""Zim flag

Revision ID: bf704baa185d
Revises: 751aecf46b88
Create Date: 2023-07-01 20:00:35.601752

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'bf704baa185d'
down_revision = '751aecf46b88'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE wrolpi_flag ADD COLUMN outdated_zims BOOLEAN DEFAULT FALSE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE wrolpi_flag DROP COLUMN outdated_zims')
