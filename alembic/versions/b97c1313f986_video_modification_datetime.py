"""Video modification_datetime

Revision ID: b97c1313f986
Revises: 3c33b1dae069
Create Date: 2022-01-25 08:00:26.944183

"""
import os
from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = 'b97c1313f986'
down_revision = '3c33b1dae069'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE video ADD COLUMN modification_datetime TIMESTAMPTZ')
    session.execute('CREATE INDEX video_modification_datetime_idx ON video USING BRIN(modification_datetime)')
    session.execute('UPDATE video SET validated=false')  # get modification time for every video duration validation.


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_modification_datetime_idx')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS modification_datetime')
