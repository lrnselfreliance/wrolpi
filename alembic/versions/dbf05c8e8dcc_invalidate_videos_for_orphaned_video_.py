"""Invalidate videos for orphaned video files.

Revision ID: dbf05c8e8dcc
Revises: 6489cd50c889
Create Date: 2022-12-07 18:26:45.017144

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'dbf05c8e8dcc'
down_revision = '6489cd50c889'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('UPDATE video SET validated=false')  # noqa


def downgrade():
    pass
