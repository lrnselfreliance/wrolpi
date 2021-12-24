"""Video indexes

Revision ID: 8df411232c17
Revises: 32d96eb9122d
Create Date: 2021-12-24 14:42:02.365100

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '8df411232c17'
down_revision = '32d96eb9122d'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('CREATE INDEX video_favorite ON video (favorite)')
    session.execute('CREATE INDEX video_view_count ON video (view_count)')
    session.execute('CREATE INDEX video_validated_poster ON video (validated_poster)')
    session.execute('CREATE INDEX video_upload_date ON video (upload_date)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_favorite')
    session.execute('DROP INDEX IF EXISTS video_view_count')
    session.execute('DROP INDEX IF EXISTS video_validated_poster')
    session.execute('DROP INDEX IF EXISTS video_upload_date')
