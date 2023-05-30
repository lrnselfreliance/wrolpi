"""Channel.refresh

Revision ID: f8c65e7e6802
Revises: 62acddc55091
Create Date: 2022-01-07 14:28:21.787842

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'f8c65e7e6802'
down_revision = '62acddc55091'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel ADD COLUMN refreshed BOOL DEFAULT false')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE channel DROP COLUMN IF EXISTS refreshed')
