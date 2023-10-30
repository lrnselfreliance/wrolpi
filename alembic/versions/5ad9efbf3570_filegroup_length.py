"""
Migrates Video.duration/.url/.viewed/Archive.url to FileGroup.length/.url/.viewed.

Revision ID: 5ad9efbf3570
Revises: 4b54ad052e2e
Create Date: 2023-10-24 09:25:33.818373

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '5ad9efbf3570'
down_revision = '4b54ad052e2e'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE file_group ADD COLUMN length INT DEFAULT 0')
    session.execute('''
        UPDATE file_group
        SET length=video.duration
        FROM video
        WHERE file_group.id = video.file_group_id
    ''')

    # Migrate Archive.url and Video.url to FileGroup.url.
    session.execute('ALTER TABLE file_group ADD COLUMN url TEXT')
    session.execute('''
        UPDATE file_group
        SET url=archive.url
        FROM archive
        WHERE file_group.id = archive.file_group_id
    ''')
    session.execute('''
        UPDATE file_group
        SET url=video.url
        FROM video
        WHERE file_group.id = video.file_group_id
    ''')

    # Migrate Archive.archive_datetime to FileGroup.download_datetime.
    session.execute('ALTER TABLE file_group ADD COLUMN download_datetime TIMESTAMP WITH TIME ZONE')
    session.execute('''
        UPDATE file_group
        SET download_datetime=archive.archive_datetime
        FROM archive
        WHERE file_group.id = archive.file_group_id
    ''')

    # Migrate Video.viewed to FileGroup.viewed.
    session.execute('ALTER TABLE file_group ADD COLUMN viewed TIMESTAMP WITH TIME ZONE')
    session.execute('''
        UPDATE file_group
        SET viewed=video.viewed
        FROM video
        WHERE file_group.id = video.file_group_id
    ''')

    session.execute('DROP INDEX IF EXISTS archive_archive_datetime_idx')
    session.execute('DROP INDEX IF EXISTS archive_url_idx')
    session.execute('DROP INDEX IF EXISTS video_url_idx')
    session.execute('DROP INDEX IF EXISTS video_viewed_idx')
    session.execute('ALTER TABLE archive DROP COLUMN IF EXISTS archive_datetime')
    session.execute('ALTER TABLE archive DROP COLUMN IF EXISTS url')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS url')
    session.execute('ALTER TABLE video DROP COLUMN IF EXISTS viewed')

    session.execute('CREATE INDEX file_group_download_datetime_idx ON file_group(download_datetime)')
    session.execute('CREATE INDEX file_group_length_idx ON file_group(length)')
    session.execute('CREATE INDEX file_group_url_idx ON file_group(url)')
    session.execute('CREATE INDEX file_group_viewed_idx ON file_group(viewed)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute('ALTER TABLE video ADD COLUMN IF NOT EXISTS duration INTEGER')
    session.execute('''
        UPDATE video
        SET duration=file_group.length
        FROM file_group
        WHERE file_group.id = video.file_group_id
    ''')

    session.execute('ALTER TABLE video ADD COLUMN IF NOT EXISTS url TEXT')
    session.execute('''
        UPDATE video
        SET url=file_group.url
        FROM file_group
        WHERE file_group.id = video.file_group_id
    ''')

    # Video has `viewed`, Archive does not.
    session.execute('ALTER TABLE video ADD COLUMN IF NOT EXISTS viewed TIMESTAMP WITH TIME ZONE')
    session.execute('''
        UPDATE video
        SET url=file_group.url
        FROM file_group
        WHERE file_group.id = video.file_group_id
    ''')

    session.execute('ALTER TABLE archive ADD COLUMN IF NOT EXISTS url TEXT')
    session.execute('''
        UPDATE archive
        SET url=file_group.url
        FROM file_group
        WHERE file_group.id = archive.file_group_id
    ''')

    session.execute('ALTER TABLE archive ADD COLUMN IF NOT EXISTS archive_datetime TIMESTAMP WITH TIME ZONE')
    session.execute('''
        UPDATE archive
        SET archive_datetime=file_group.download_datetime
        FROM file_group
        WHERE file_group.id = archive.file_group_id
    ''')

    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS download_datetime')
    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS length')
    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS url')
    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS viewed')
    session.execute('DROP INDEX IF EXISTS file_group_download_datetime_idx')
    session.execute('DROP INDEX IF EXISTS file_group_length_idx')
    session.execute('DROP INDEX IF EXISTS file_group_url_idx')
    session.execute('DROP INDEX IF EXISTS file_group_viewed_idx')

    session.execute('CREATE INDEX IF NOT EXISTS archive_archive_datetime_idx ON archive(archive_datetime)')
    session.execute('CREATE INDEX IF NOT EXISTS archive_url_idx ON archive(url)')
    session.execute('CREATE INDEX IF NOT EXISTS video_duration_idx ON video(duration)')
    session.execute('CREATE INDEX IF NOT EXISTS video_url_idx ON video(url)')
    session.execute('CREATE INDEX IF NOT EXISTS video_viewed_idx ON video(viewed)')
