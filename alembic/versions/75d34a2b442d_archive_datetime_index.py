"""Archive datetime index.

Revision ID: 75d34a2b442d
Revises: f9928a3b6bc5
Create Date: 2023-05-15 13:09:47.661940

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '75d34a2b442d'
down_revision = 'f9928a3b6bc5'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('CREATE INDEX archive_datetime_idx ON archive(archive_datetime)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS archive_datetime_idx')
