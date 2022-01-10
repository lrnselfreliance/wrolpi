"""Video source_id index.

Revision ID: f2c6326cad29
Revises: f8c65e7e6802
Create Date: 2022-01-10 08:27:39.082067

"""
import os
from alembic import op
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = 'f2c6326cad29'
down_revision = 'f8c65e7e6802'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('CREATE INDEX video_source_id_idx ON video(source_id)')
    session.execute('ALTER INDEX video_censored RENAME TO video_censored_idx')
    session.execute('ALTER INDEX video_favorite RENAME TO video_favorite_idx')
    session.execute('ALTER INDEX video_view_count RENAME TO video_view_count_idx')
    session.execute('ALTER INDEX video_validated_poster RENAME TO video_validated_poster_idx')
    session.execute('ALTER INDEX video_upload_date RENAME TO video_upload_date_idx')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('DROP INDEX IF EXISTS video_source_id_idx')
    session.execute('ALTER INDEX video_censored_idx RENAME TO video_censored')
    session.execute('ALTER INDEX video_favorite_idx RENAME TO video_favorite')
    session.execute('ALTER INDEX video_view_count_idx RENAME TO video_view_count')
    session.execute('ALTER INDEX video_validated_poster_idx RENAME TO video_validated_poster')
    session.execute('ALTER INDEX video_upload_date_idx RENAME TO video_upload_date')
