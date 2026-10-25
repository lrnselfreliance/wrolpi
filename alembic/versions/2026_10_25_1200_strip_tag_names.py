"""Tag names have no leading or trailing whitespace.

A Tag whose name had whitespace is renamed.  Tags whose names are the same once stripped are merged into one: it
keeps every tagged file, Zim entry and Collection, and the first color (by Tag id) of the merged Tags.  Downloads
and the config files that name Tags are rewritten the same way, so the next import finds them in step with the
database (an import of the old names would create the padded Tags again, or delete the stripped ones).

Revision ID: 2026_10_25_1200
Revises: 2026_10_24_1200
"""
import json
import logging

import yaml
from alembic import op

from wrolpi.common import get_media_directory, write_config_data

# revision identifiers, used by Alembic.
revision = '2026_10_25_1200'
down_revision = '2026_10_24_1200'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

# The configs which name Tags.
CONFIG_FILES = ('tags.yaml', 'download_manager.yaml', 'channels.yaml', 'domains.yaml', 'playlists.yaml',
                'repos.yaml', 'videos_downloader.yaml', 'archives_downloader.yaml')


def _strip(name):
    """A Tag name without its whitespace; a name that would be empty is kept (it cannot be renamed)."""
    if isinstance(name, str) and name.strip():
        return name.strip()
    return name


def _strip_names(names: list) -> list:
    stripped = list()
    for name in map(_strip, names):
        if name not in stripped:
            stripped.append(name)
    return stripped


def _strip_nested(data):
    """Strip the Tag names in a config's (or a Download's settings') `tag_name`, `tag_names` and
    `channel_tag_name` values, at any depth."""
    if isinstance(data, list):
        return [_strip_nested(i) for i in data]
    if not isinstance(data, dict):
        return data
    result = dict()
    for key, value in data.items():
        if key == 'tag_name':
            value = _strip(value)
        elif key in ('tag_names', 'channel_tag_name') and isinstance(value, list):
            value = _strip_names(value)
        else:
            value = _strip_nested(value)
        result[key] = value
    return result


def _strip_rows(rows: list, key_length: int) -> list:
    """tags.yaml's tag_files or tag_zims, each row keyed by its first `key_length` values (the Tag name first)."""
    result, seen = list(), set()
    for row in rows:
        if isinstance(row, list) and row:
            row = [_strip(row[0]), *row[1:]]
            key = json.dumps(row[:key_length], default=str)
            if key in seen:
                continue
            seen.add(key)
        result.append(row)
    return result


def _strip_tags_config(config: dict) -> dict:
    config = dict(config)
    if isinstance(config.get('tags'), dict):
        tags = dict()
        for name, attrs in config['tags'].items():
            stripped = _strip(name)
            if stripped not in tags:
                tags[stripped] = attrs
            elif isinstance(attrs, dict) and attrs.get('color') and not (tags[stripped] or dict()).get('color'):
                # The first color of the merged Tags.
                tags[stripped] = {**(tags[stripped] or dict()), 'color': attrs['color']}
        config['tags'] = tags
    if isinstance(config.get('tag_files'), list):
        config['tag_files'] = _strip_rows(config['tag_files'], 2)
    if isinstance(config.get('tag_zims'), list):
        config['tag_zims'] = _strip_rows(config['tag_zims'], 3)
    return config


def strip_tag_names_in_configs():
    config_directory = get_media_directory() / 'config'
    for file_name in CONFIG_FILES:
        file = config_directory / file_name
        if not file.is_file():
            continue
        try:
            with file.open('rt') as fh:
                config = yaml.load(fh, Loader=yaml.CSafeLoader)
        except Exception as e:
            logger.error(f'Cannot strip Tag names of invalid config: {file}', exc_info=e)
            continue
        if not isinstance(config, dict):
            continue
        stripped = _strip_tags_config(config) if file_name == 'tags.yaml' else config
        stripped = _strip_nested(stripped)
        if stripped != config:
            logger.warning(f'Stripping whitespace from Tag names in {file}')
            write_config_data(stripped, file, width=500 if file_name == 'tags.yaml' else 90)


def strip_tag_names_in_db(connection):
    groups = dict()
    for id_, name, color in connection.exec_driver_sql('SELECT id, name, color FROM tag ORDER BY id').fetchall():
        groups.setdefault(_strip(name), list()).append((id_, name, color))

    for stripped, tags in groups.items():
        if all(name == stripped for _, name, _ in tags):
            continue
        # Keep the Tag already named this, if any, otherwise the oldest.
        survivor_id = next((id_ for id_, name, _ in tags if name == stripped), tags[0][0])
        color = next((color for _, _, color in tags if color), None)
        for id_, name, _ in tags:
            if id_ == survivor_id:
                continue
            logger.warning(f'Merging Tag {name!r} into {stripped!r}')
            connection.exec_driver_sql(
                'INSERT OR IGNORE INTO tag_file (tag_id, file_group_id, created_at)'
                ' SELECT ?, file_group_id, created_at FROM tag_file WHERE tag_id = ?', (survivor_id, id_))
            connection.exec_driver_sql(
                'INSERT OR IGNORE INTO tag_zim (tag_id, zim_id, zim_entry, created_at)'
                ' SELECT ?, zim_id, zim_entry, created_at FROM tag_zim WHERE tag_id = ?', (survivor_id, id_))
            connection.exec_driver_sql('DELETE FROM tag_file WHERE tag_id = ?', (id_,))
            connection.exec_driver_sql('DELETE FROM tag_zim WHERE tag_id = ?', (id_,))
            connection.exec_driver_sql('UPDATE collection SET tag_id = ? WHERE tag_id = ?', (survivor_id, id_))
            connection.exec_driver_sql('DELETE FROM tag WHERE id = ?', (id_,))
        logger.warning(f'Renaming Tag to {stripped!r}')
        connection.exec_driver_sql('UPDATE tag SET name = ?, color = ? WHERE id = ?', (stripped, color, survivor_id))

    # The Downloads which apply them (download_manager.yaml is stripped the same way).
    downloads = connection.exec_driver_sql(
        'SELECT id, tag_names, settings FROM download WHERE tag_names IS NOT NULL OR settings IS NOT NULL').fetchall()
    for id_, tag_names, settings in downloads:
        tag_names, settings = json.loads(tag_names) if tag_names else None, json.loads(settings) if settings else None
        new_tag_names = _strip_names(tag_names) if isinstance(tag_names, list) else tag_names
        new_settings = _strip_nested(settings)
        if new_tag_names != tag_names or new_settings != settings:
            connection.exec_driver_sql(
                'UPDATE download SET tag_names = ?, settings = ? WHERE id = ?',
                (json.dumps(new_tag_names) if new_tag_names is not None else None,
                 json.dumps(new_settings) if new_settings is not None else None, id_))


def upgrade():
    strip_tag_names_in_db(op.get_bind())
    strip_tag_names_in_configs()


def downgrade():
    # Whitespace that was stripped is not restored.
    pass
