"""Increase file size column.

Revision ID: aac864072193
Revises: 467235201c70
Create Date: 2022-06-22 17:34:33.635528

"""
import os
from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = 'aac864072193'
down_revision = '467235201c70'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file ALTER COLUMN size TYPE bigint')


def downgrade():
    pass
