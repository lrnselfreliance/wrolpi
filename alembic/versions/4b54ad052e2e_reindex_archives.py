"""Reindex archives.

Revision ID: 4b54ad052e2e
Revises: 6b0b249a4f81
Create Date: 2023-10-20 13:28:55.517086

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '4b54ad052e2e'
down_revision = '6b0b249a4f81'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Archives must be re-indexed because of the previous revision.
    session.execute("UPDATE file_group SET indexed=false WHERE model='archive'")
    session.execute("DELETE FROM archive")  # noqa


def downgrade():
    pass
