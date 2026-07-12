import pathlib
import shutil
from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, get_media_directory, get_relative_to_media_directory, logger
from wrolpi.db import get_db_session
from wrolpi.events import Events
from wrolpi.switches import ActivateSwitchMethod, register_switch_handler

logger = logger.getChild(__name__)

__all__ = ['PlaylistsConfig', 'playlists_config', 'save_playlists_config', 'get_playlists_config']


@dataclass
class PlaylistsConfigValidator:
    """Validator for the playlists config file."""
    version: int = 0
    playlists: List[dict] = field(default_factory=list)


class PlaylistsConfig(ConfigFile):
    """Config file for playlists (Collections with kind='playlist').

    Unlike other collection kinds, playlists are user-curated and ordered, with no other config
    that owns them — so this config stores each playlist's metadata AND its ordered item list
    (files/zim-articles/urls), making the config the source of truth that survives a DB rebuild.

    Format:
        playlists:
          - name: "Fire Making"
            description: "..."
            tag_name: "..."          # optional
            items:
              - file: "videos/foo.mp4"
              - zim: "zims/wikipedia.zim"
                entry: "A/Fire"
                title: "Making Fire"
              - url: "/map?lat=1&lon=2&z=10"
                title: "The spot"
    """
    file_name = 'playlists.yaml'
    validator = PlaylistsConfigValidator
    default_config = dict(version=0, playlists=[])
    width = 120

    @property
    def playlists(self) -> List[dict]:
        return self._config.get('playlists', [])

    def import_config(self, file: pathlib.Path = None, send_events=False):
        """Import playlists (and their ordered items) from the config into the database."""
        from modules.zim.models import Zim
        from wrolpi.files.models import FileGroup
        from wrolpi.tags import Tag

        from .models import Collection, CollectionItem

        file = file or self.get_file()
        file_str = str(self.get_relative_file())

        # A missing config is NOT an empty config (mirrors ChannelsConfig).  Deleting here would
        # cascade: the sync prunes the on-disk playlist dirs and the next dump writes an empty
        # config -- a single lost file would permanently destroy every playlist.
        if not file.is_file():
            logger.info(f'No playlists config file, skipping import: {file_str}')
            self.successful_import = True
            return

        super().import_config(file, send_events)
        playlists_data = self._config.get('playlists', [])

        # An empty playlists list never deletes DB records (mirrors ChannelsConfig).  Deleting all
        # playlists is done through the API, which dumps the resulting (empty) config itself.
        if not playlists_data:
            logger.info(f'No playlists in config, preserving existing DB playlists: {file_str}')
            self.successful_import = True
            return

        try:
            with get_db_session(commit=True) as session:
                imported_names = set()
                for data in playlists_data:
                    name = data.get('name')
                    if not name:
                        logger.error(f'Playlist config entry has no name, skipping: {data}')
                        self.import_skipped += 1
                        continue

                    collection = session.query(Collection).filter_by(
                        name=name, kind='playlist').one_or_none()
                    if not collection:
                        collection = Collection(name=name, kind='playlist')
                        session.add(collection)
                    collection.description = data.get('description')

                    # Optional custom directory (media-relative); None when not customized.
                    directory = data.get('directory')
                    collection.directory = (get_media_directory() / directory) if directory else None

                    tag_name = data.get('tag_name')
                    collection.tag = Tag.get_by_name(session, tag_name) if tag_name else None
                    session.flush([collection])

                    # Rebuild items to match the config's order exactly.
                    for item in list(collection.items):
                        session.delete(item)
                    session.flush()

                    position = 1
                    for item_data in (data.get('items') or []):
                        item = None
                        if 'file' in item_data:
                            path = get_media_directory() / item_data['file']
                            fg = session.query(FileGroup).filter_by(primary_path=str(path)).one_or_none()
                            if fg:
                                item = CollectionItem(collection_id=collection.id, item_kind='file',
                                                      file_group_id=fg.id)
                            else:
                                logger.warning(f'Playlist {name!r}: file not indexed, skipping '
                                               f'{item_data["file"]!r}')
                                self.import_skipped += 1
                        elif 'zim' in item_data:
                            zpath = get_media_directory() / item_data['zim']
                            zim = session.query(Zim).filter_by(path=str(zpath)).one_or_none()
                            if zim:
                                item = CollectionItem(collection_id=collection.id, item_kind='zim',
                                                      zim_id=zim.id, zim_entry=item_data.get('entry'))
                            else:
                                logger.warning(f'Playlist {name!r}: zim not found, skipping '
                                               f'{item_data["zim"]!r}')
                                self.import_skipped += 1
                        elif 'url' in item_data:
                            item = CollectionItem(collection_id=collection.id, item_kind='url',
                                                  url=item_data['url'])
                        if item is not None:
                            item.title = item_data.get('title')
                            item.position = position
                            position += 1
                            session.add(item)

                    session.flush()
                    imported_names.add(name)

                # Delete playlists that are no longer present in the config.
                for collection in session.query(Collection).filter_by(kind='playlist').all():
                    if collection.name not in imported_names:
                        logger.info(f'Deleting playlist {collection.name!r} (no longer in config)')
                        session.delete(collection)

            logger.info(f'Imported {len(imported_names)} playlists from {file_str}')
            self.successful_import = True
        except Exception as e:
            self.successful_import = False
            message = f'Failed to import {file_str} config!'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_import_failed(message)
            raise

    def preview_backup_import(self, backup_date: str, mode: str) -> dict:
        """Preview which playlists a backup import would add/remove (keyed by playlist name)."""
        backup_file = self._get_backup_file(backup_date)
        backup_data = self.read_config_file(backup_file)
        current_data = self.read_config_file() if self.get_file().is_file() else dict(playlists=[], version=0)

        backup_playlists = backup_data.get('playlists', [])
        current_playlists = current_data.get('playlists', [])

        current_names = {p.get('name') for p in current_playlists if p.get('name')}
        backup_names = {p.get('name') for p in backup_playlists if p.get('name')}

        add = []
        remove = []
        unchanged = 0

        for playlist in backup_playlists:
            name = playlist.get('name')
            if name and name not in current_names:
                add.append(dict(type='playlist', name=name, items=len(playlist.get('items') or [])))
            elif name:
                unchanged += 1
        if mode == 'overwrite':
            for name in sorted(current_names - backup_names):
                remove.append(dict(type='playlist', name=name))

        return dict(mode=mode, add=add, remove=remove, unchanged=unchanged)

    def import_backup(self, backup_date: str, mode: str, send_events: bool = False):
        """Restore playlists from a dated backup of playlists.yaml.

        'overwrite' replaces the config with the backup; 'merge' adds backup playlists whose names
        are not already in the current config.  Either way the result is imported into the DB.
        """
        self._preserve_current_config()
        backup_file = self._get_backup_file(backup_date)
        config_file = self.get_file()

        if mode == 'overwrite':
            config_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, config_file)
        elif mode == 'merge':
            backup_data = self.read_config_file(backup_file)
            current_data = self.read_config_file() if config_file.is_file() else dict(playlists=[], version=0)

            current_names = {p.get('name') for p in current_data.get('playlists', []) if p.get('name')}
            merged_playlists = list(current_data.get('playlists', []))
            for playlist in backup_data.get('playlists', []):
                if playlist.get('name') and playlist['name'] not in current_names:
                    merged_playlists.append(playlist)

            merged_data = dict(
                playlists=merged_playlists,
                version=current_data.get('version', 0) + 1,
            )
            config_file.parent.mkdir(parents=True, exist_ok=True)
            self.write_config_data(merged_data, config_file)

        self.import_config(send_events=send_events)
        # Materialize the restored playlists on disk.
        from .sync import sync_playlists_directory
        sync_playlists_directory.activate_switch()

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all playlists (with their ordered items) to the config file."""
        from .models import Collection

        # playlists.yaml is derived from the database (the source of truth here), so the dump should
        # always win.  Sync our in-memory version up to the on-disk version first, otherwise a Sanic
        # worker (or freshly-restarted process) that hasn't re-imported would refuse to overwrite a
        # newer on-disk config.
        target = file or self.get_file()
        try:
            if target.exists():
                disk_version = (self.read_config_file(target) or {}).get('version') or 0
                if disk_version > (self._config.get('version') or 0):
                    self._config['version'] = disk_version
        except Exception as e:
            logger.warning(f'Could not read existing playlists config version: {e}')

        with get_db_session() as session:
            playlists = session.query(Collection).filter_by(kind='playlist') \
                .order_by(Collection.name).all()
            data = []
            for collection in playlists:
                entry = {'name': collection.name}
                if collection.description:
                    entry['description'] = collection.description
                if collection.tag_name:
                    entry['tag_name'] = collection.tag_name
                if collection.directory:
                    # Custom playlist directory; stored relative to the media directory.
                    entry['directory'] = str(get_relative_to_media_directory(collection.directory))
                entry['items'] = [c for c in (i.to_config() for i in collection.items) if c]
                data.append(entry)
            self._config['playlists'] = data

        logger.info(f'Dumping {len(data)} playlists to config')
        self.save(file, send_events, overwrite)


# Global instance
playlists_config = PlaylistsConfig()


@register_switch_handler('save_playlists_config')
def save_playlists_config():
    """Save the playlists config when the switch is activated."""
    playlists_config.background_dump.activate_switch()


def get_playlists_config() -> PlaylistsConfig:
    return playlists_config


@register_switch_handler('import_playlists_config')
def import_playlists_config():
    """Re-import playlists.yaml into the database.

    Activated when a global refresh completes: after a DB rebuild, playlists.yaml is imported at
    startup before any files are indexed, so its file/zim items are skipped.  The config still
    holds them; once the refresh has re-indexed the files, this re-import restores those items.
    """
    playlists_config.import_config()
    # Restored items need their hardlinks/stubs re-created.
    from .sync import sync_playlists_directory
    sync_playlists_directory.activate_switch()


save_playlists_config: ActivateSwitchMethod
import_playlists_config: ActivateSwitchMethod
