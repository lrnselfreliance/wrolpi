"""Reindex pdfs

Revision ID: d0bbe45e56c3
Revises: dbf05c8e8dcc
Create Date: 2022-12-09 12:27:18.908533

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd0bbe45e56c3'
down_revision = 'dbf05c8e8dcc'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute("UPDATE file SET indexed=false WHERE mimetype = 'application/pdf'")


def downgrade():
    pass
