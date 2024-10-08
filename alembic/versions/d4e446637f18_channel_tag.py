"""Channel tag

Revision ID: d4e446637f18
Revises: 2bfb3b50b178
Create Date: 2024-08-03 17:49:17.133086

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd4e446637f18'
down_revision = '2bfb3b50b178'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE channel ADD COLUMN IF NOT EXISTS tag_id INTEGER REFERENCES tag(id)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS tag_id')
