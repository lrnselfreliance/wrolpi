"""Fix media paths incorrectly resolved against /opt/wrolpi.

MediaPathType.process_bind_param() was calling .absolute() on relative paths,
which resolves against the current working directory (cwd) instead of the
media directory. In production, cwd is /opt/wrolpi, so paths like
'archive/spiegel.de' became '/opt/wrolpi/archive/spiegel.de' instead of
'/media/wrolpi/archive/spiegel.de'.

This migration fixes any corrupted paths in the database and saves the
corrected paths to config files.

Revision ID: b2b9700f5048
Revises: a1b2c3d4e5f6
Create Date: 2026-01-27
"""
import os
import pathlib

import yaml
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2b9700f5048'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def get_relative_path(absolute_path: str, media_directory: str) -> str:
    """Convert absolute path to relative path under media directory."""
    if absolute_path and absolute_path.startswith(media_directory):
        return absolute_path[len(media_directory):].lstrip('/')
    return absolute_path


def save_config_file(config: dict, file_path: pathlib.Path, width: int = 120):
    """Write config dict to YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open('wt') as fh:
        yaml.dump(config, fh, width=width, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())


def upgrade():
    connection = op.get_bind()

    # Fix collection.directory
    result = connection.execute(sa.text("""
        UPDATE collection
        SET directory = REPLACE(directory, '/opt/wrolpi/', '/media/wrolpi/')
        WHERE directory LIKE '/opt/wrolpi/%'
    """))
    if result.rowcount:
        print(f"Fixed {result.rowcount} collection directory paths")

    # Fix file_group.directory
    result = connection.execute(sa.text("""
        UPDATE file_group
        SET directory = REPLACE(directory, '/opt/wrolpi/', '/media/wrolpi/')
        WHERE directory LIKE '/opt/wrolpi/%'
    """))
    if result.rowcount:
        print(f"Fixed {result.rowcount} file_group directory paths")

    # Fix file_group.primary_path
    result = connection.execute(sa.text("""
        UPDATE file_group
        SET primary_path = REPLACE(primary_path, '/opt/wrolpi/', '/media/wrolpi/')
        WHERE primary_path LIKE '/opt/wrolpi/%'
    """))
    if result.rowcount:
        print(f"Fixed {result.rowcount} file_group primary_path paths")

    # Fix download.destination
    result = connection.execute(sa.text("""
        UPDATE download
        SET destination = REPLACE(destination, '/opt/wrolpi/', '/media/wrolpi/')
        WHERE destination LIKE '/opt/wrolpi/%'
    """))
    if result.rowcount:
        print(f"Fixed {result.rowcount} download destination paths")

    # Save corrected paths to config files directly (bypass config framework which needs SharedContext)
    try:
        from wrolpi.common import get_media_directory
        media_dir = str(get_media_directory())
        config_dir = get_media_directory() / 'config'

        # Save domains config
        domains_result = connection.execute(sa.text("""
            SELECT id, name, kind, description, directory, file_format
            FROM collection
            WHERE kind = 'domain'
            ORDER BY name
        """))
        domains_collections = []
        for row in domains_result:
            collection_config = {'name': row[1], 'kind': row[2]}
            if row[3]:  # description
                collection_config['description'] = row[3]
            if row[4]:  # directory
                collection_config['directory'] = get_relative_path(row[4], media_dir + '/')
            if row[5]:  # file_format
                collection_config['file_format'] = row[5]
            # Get tag name if exists
            tag_result = connection.execute(sa.text("""
                SELECT t.name FROM tag t
                JOIN collection c ON c.tag_id = t.id
                WHERE c.id = :id
            """), {'id': row[0]}).first()
            collection_config['tag_name'] = tag_result[0] if tag_result else None
            domains_collections.append(collection_config)

        # Read existing config to preserve version
        domains_file = config_dir / 'domains.yaml'
        version = 0
        if domains_file.exists():
            with domains_file.open() as f:
                existing = yaml.safe_load(f) or {}
                version = existing.get('version', 0)

        domains_config = {'version': version + 1, 'collections': domains_collections}
        save_config_file(domains_config, domains_file)
        print(f"Saved domains config with {len(domains_collections)} collections")

        # Save channels config
        # Columns: 0=id, 1=name, 2=kind, 3=description, 4=directory, 5=file_format,
        #          6=url, 7=source_id, 8=generate_posters, 9=calculate_duration, 10=download_missing_data
        channels_result = connection.execute(sa.text("""
            SELECT c.id, c.name, c.kind, c.description, c.directory, c.file_format,
                   ch.url, ch.source_id, ch.generate_posters, ch.calculate_duration,
                   ch.download_missing_data
            FROM collection c
            JOIN channel ch ON ch.collection_id = c.id
            WHERE c.kind = 'channel'
            ORDER BY c.name
        """))
        channels_list = []
        for row in channels_result:
            channel_config = {'name': row[1]}
            if row[4]:  # directory
                channel_config['directory'] = get_relative_path(row[4], media_dir + '/')
            if row[6]:  # url
                channel_config['url'] = row[6]
            if row[7]:  # source_id
                channel_config['source_id'] = row[7]
            channel_config['generate_posters'] = row[8]
            channel_config['calculate_duration'] = row[9]
            channel_config['download_missing_data'] = row[10]
            if row[5]:  # file_format
                channel_config['file_format'] = row[5]
            # Get tag name if exists
            tag_result = connection.execute(sa.text("""
                SELECT t.name FROM tag t
                JOIN collection c ON c.tag_id = t.id
                WHERE c.id = :id
            """), {'id': row[0]}).first()
            channel_config['tag_name'] = tag_result[0] if tag_result else None
            # Get downloads for this channel's collection
            downloads_result = connection.execute(sa.text("""
                SELECT url, frequency FROM download
                WHERE collection_id = :collection_id
            """), {'collection_id': row[0]})
            downloads = [{'url': d[0], 'frequency': d[1]} for d in downloads_result]
            if downloads:
                channel_config['downloads'] = downloads
            channels_list.append(channel_config)

        # Read existing config to preserve version
        channels_file = config_dir / 'channels.yaml'
        version = 0
        if channels_file.exists():
            with channels_file.open() as f:
                existing = yaml.safe_load(f) or {}
                version = existing.get('version', 0)

        channels_config = {'version': version + 1, 'channels': channels_list}
        save_config_file(channels_config, channels_file)
        print(f"Saved channels config with {len(channels_list)} channels")

    except Exception as e:
        print(f"Warning: Could not save configs: {e}")


def downgrade():
    # Data fix, no meaningful downgrade
    pass
