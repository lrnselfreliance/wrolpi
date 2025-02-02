"""Zim auto search

Revision ID: dc6637ced17b
Revises: 1f2325523525
Create Date: 2025-01-30 19:02:32.692428

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'dc6637ced17b'
down_revision = '1f2325523525'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE zim ADD COLUMN auto_search BOOLEAN DEFAULT TRUE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE zim DROP COLUMN IF EXISTS auto_search')
