"""Video validated.

Revision ID: 3c33b1dae069
Revises: f2c6326cad29
Create Date: 2022-01-13 16:14:23.409242

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '3c33b1dae069'
down_revision = 'f2c6326cad29'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE video ADD COLUMN validated BOOLEAN DEFAULT FALSE')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS validated_poster')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS validated')
    session.execute('ALTER TABLE video ADD COLUMN validated_poster BOOLEAN DEFAULT FALSE')
