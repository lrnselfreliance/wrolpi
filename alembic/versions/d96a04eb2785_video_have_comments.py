"""Video.have_comments

Revision ID: d96a04eb2785
Revises: 365c985893b8
Create Date: 2024-02-27 16:57:29.831210

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd96a04eb2785'
down_revision = '365c985893b8'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video ADD COLUMN have_comments BOOLEAN DEFAULT FALSE')
    session.execute('ALTER TABLE video ADD COLUMN comments_failed BOOLEAN DEFAULT FALSE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS have_comments')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS comments_failed')
