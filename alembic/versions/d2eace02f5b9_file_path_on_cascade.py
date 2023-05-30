"""file.path on cascade

Revision ID: d2eace02f5b9
Revises: 70db5ba8763d
Create Date: 2022-09-28 15:14:43.306819

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = 'd2eace02f5b9'
down_revision = '70db5ba8763d'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('''
    ALTER TABLE video DROP CONSTRAINT video_caption_path_fkey;
    ALTER TABLE video DROP CONSTRAINT video_info_json_path_fkey;
    ALTER TABLE video DROP CONSTRAINT video_poster_path_fkey;
    ALTER TABLE video DROP CONSTRAINT video_video_path_fkey;
    ALTER TABLE video ADD FOREIGN KEY (caption_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE video ADD FOREIGN KEY (info_json_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE video ADD FOREIGN KEY (poster_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE video ADD FOREIGN KEY (video_path) REFERENCES file ON DELETE CASCADE;
    ''')

    session.execute('''
    ALTER TABLE archive DROP CONSTRAINT archive_readability_json_path_fkey;
    ALTER TABLE archive DROP CONSTRAINT archive_readability_path_fkey;
    ALTER TABLE archive DROP CONSTRAINT archive_readability_txt_path_fkey;
    ALTER TABLE archive DROP CONSTRAINT archive_screenshot_path_fkey;
    ALTER TABLE archive DROP CONSTRAINT archive_singlefile_path_fkey;
    ALTER TABLE archive ADD FOREIGN KEY (readability_json_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE archive ADD FOREIGN KEY (readability_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE archive ADD FOREIGN KEY (readability_txt_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE archive ADD FOREIGN KEY (screenshot_path) REFERENCES file ON DELETE CASCADE;
    ALTER TABLE archive ADD FOREIGN KEY (singlefile_path) REFERENCES file ON DELETE CASCADE;
    ''')

    if not DOCKERIZED:
        session.execute('ALTER TABLE public.file OWNER TO wrolpi')
        session.execute('ALTER TABLE public.video OWNER TO wrolpi')
        session.execute('ALTER TABLE public.domains OWNER TO wrolpi')
        session.execute('ALTER TABLE public.archive OWNER TO wrolpi')


def downgrade():
    pass
