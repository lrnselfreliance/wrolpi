"""Archive url index.

Revision ID: 13542a230c78
Revises: c72d305cf11e
Create Date: 2022-11-02 15:19:42.408462

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '13542a230c78'
down_revision = 'c72d305cf11e'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('CREATE INDEX IF NOT EXISTS archive_url_idx ON archive(url)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('DROP INDEX IF EXISTS archive_url_idx')
