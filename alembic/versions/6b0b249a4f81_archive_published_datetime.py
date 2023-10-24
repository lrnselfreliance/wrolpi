"""Archive published_datetime

Revision ID: 6b0b249a4f81
Revises: 4c8da5502c8a
Create Date: 2023-10-20 12:54:55.879180

"""
import os

from alembic import op
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = '6b0b249a4f81'
down_revision = '4c8da5502c8a'
branch_labels = None
depends_on = None

DOCKERIZED = True if os.environ.get('DOCKER', '').lower().startswith('t') else False


def upgrade():
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute('ALTER TABLE file_group ADD COLUMN author TEXT')
    session.execute('ALTER TABLE file_group ADD COLUMN published_datetime TIMESTAMP WITH TIME ZONE')
    session.execute('ALTER TABLE file_group ADD COLUMN published_modified_datetime TIMESTAMP WITH TIME ZONE')

    # Migrate Video.upload_date to FileGroup.published_datetime.
    session.execute('''
        UPDATE file_group
        SET published_datetime=upload_date
        FROM video
        WHERE file_group.id = video.file_group_id
    ''')

    session.execute('CREATE INDEX IF NOT EXISTS file_group_author_idx ON file_group(author)')
    session.execute('CREATE INDEX IF NOT EXISTS file_group_published_datetime_idx ON file_group(published_datetime)')
    session.execute('CREATE INDEX IF NOT EXISTS file_group_published_modified_datetime_idx'
                    ' ON file_group(published_modified_datetime)')


def downgrade():
    bind = op.get_bind()
    session = Session(bind=bind)

    # Migrate FileGroup.published_datetime to Video.upload_date.
    session.execute('''
        UPDATE video
        SET upload_date=published_datetime
        FROM file_group
        WHERE file_group.id = video.file_group_id
    ''')

    session.execute('DROP INDEX IF EXISTS file_group_author_idx')
    session.execute('DROP INDEX IF EXISTS file_group_published_datetime_idx')
    session.execute('DROP INDEX IF EXISTS file_group_published_modified_datetime_idx')

    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS author')
    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS published_datetime')
    session.execute('ALTER TABLE file_group DROP COLUMN IF EXISTS published_modified_datetime')
