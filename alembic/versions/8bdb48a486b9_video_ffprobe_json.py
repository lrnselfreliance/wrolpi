"""Video ffprobe json.

Revision ID: 8bdb48a486b9
Revises: bf704baa185d
Create Date: 2023-07-24 10:59:17.426100

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '8bdb48a486b9'
down_revision = 'bf704baa185d'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video ADD COLUMN ffprobe_json JSON')
    # Re-index all videos so the ffprobe data is fetched.
    session.execute("UPDATE file_group SET indexed=false WHERE mimetype like 'video/%'")


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS ffprobe_json')
