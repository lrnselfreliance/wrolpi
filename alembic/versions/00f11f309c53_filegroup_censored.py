"""FileGroup.censored

Revision ID: 00f11f309c53
Revises: 1c041aeee0fc
Create Date: 2024-06-17 14:02:09.881477

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '00f11f309c53'
down_revision = '1c041aeee0fc'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file_group ADD COLUMN censored BOOLEAN DEFAULT FALSE')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS censored')
