"""file-slug

Revision ID: 0c6fc8ef6165
Revises: d4e446637f18
Create Date: 2024-08-21 22:34:24.760842

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '0c6fc8ef6165'
down_revision = 'd4e446637f18'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file_group ADD COLUMN slug TEXT UNIQUE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS slug')
