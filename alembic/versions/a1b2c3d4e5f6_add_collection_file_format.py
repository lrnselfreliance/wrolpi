"""add_collection_file_format

Revision ID: a1b2c3d4e5f6
Revises: 76add63ed225
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '76add63ed225'
branch_labels = None
depends_on = None


def upgrade():
    # Add file_format column to collection table
    # This stores the file_name_format used when files were last organized
    op.add_column('collection', sa.Column('file_format', sa.String(), nullable=True))

    # Set default values from current configs so existing collections don't need reorganization
    from modules.archive.lib import get_archive_downloader_config
    from modules.videos.lib import get_videos_downloader_config

    connection = op.get_bind()

    # Update domain collections with archive config's file_name_format
    archive_config = get_archive_downloader_config()
    if archive_config.file_name_format:
        connection.execute(
            sa.text("UPDATE collection SET file_format = :format WHERE kind = 'domain'"),
            {'format': archive_config.file_name_format}
        )

    # Update channel collections with video config's file_name_format
    video_config = get_videos_downloader_config()
    if video_config.file_name_format:
        connection.execute(
            sa.text("UPDATE collection SET file_format = :format WHERE kind = 'channel'"),
            {'format': video_config.file_name_format}
        )


def downgrade():
    op.drop_column('collection', 'file_format')
