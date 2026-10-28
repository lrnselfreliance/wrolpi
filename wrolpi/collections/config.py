import pathlib
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import insert
from sqlalchemy.orm import Session

from wrolpi.common import ConfigFile, get_media_directory, get_relative_to_media_directory, logger
from wrolpi.config_import import ConfigSection, SectionDiff, Unreadable, chunks, media_relative
from wrolpi.config_version import count_config_change
from wrolpi.db import get_db_session
from wrolpi.switches import ActivateSwitchMethod, register_switch_handler
from wrolpi.files.progress import RecentlyViewedConfig, save_recently_viewed_config
from wrolpi.tags import TagFile, TagsConfig, save_tags_config

logger = logger.getChild(__name__)

__all__ = ['PlaylistsConfig', 'playlists_config', 'save_playlists_config', 'get_playlists_config']


def _playlist_tag_names(rows) -> Set[str]:
    return {i['tag_name'] for i in rows if i['tag_name']}


# The position in an invalid item key that stands for all of a playlist's items (its `items` is not a list).
ITEMS_UNREADABLE = 0


def _playlist_name(data) -> Optional[str]:
    """The name of a playlist entry, or None when the entry is malformed."""
    name = data.get('name') if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


class PlaylistsSection(ConfigSection):
    """playlists.yaml's playlists (Collections with kind 'playlist'), keyed by name."""
    name = 'playlists'

    def file_rows(self, config: dict) -> Tuple[Dict[str, dict], Set[str]]:
        from .models import validate_collection_directory
        rows, invalid = dict(), set()
        for position, data in enumerate(config.get('playlists') or []):
            name = _playlist_name(data)
            if not name:
                logger.error(f'Playlist config entry has no name, skipping: {data!r}')
                # Counted as skipped (see `Unreadable`).
                invalid.add(Unreadable(position))
                continue
            try:
                rows[name] = dict(
                    description=data.get('description') or None,
                    # Optional custom directory (media-relative, inside the media directory); None when not customized.
                    directory=media_relative(validate_collection_directory(data['directory']))
                    if data.get('directory') else None,
                    tag_name=data.get('tag_name') or None,
                )
            except Exception as e:
                logger.error(f'Skipping invalid playlist in config: {name}', exc_info=e)
                invalid.add(name)
        return rows, invalid

    def db_rows(self, session: Session) -> Dict[str, dict]:
        from wrolpi.tags import Tag
        from .models import Collection
        query = session.query(Collection.name, Collection.description, Collection.directory, Tag.name) \
            .outerjoin(Tag, Tag.id == Collection.tag_id) \
            .filter(Collection.kind == 'playlist')
        return {name: dict(description=description or None,
                           directory=media_relative(directory) if directory else None,
                           tag_name=tag_name)
                for name, description, directory, tag_name in query}

    def upsert(self, session: Session, rows: Dict[str, dict]):
        from wrolpi.tags import Tag
        from .models import Collection
        existing = {i.name: i for i in
                    session.query(Collection).filter(Collection.kind == 'playlist', Collection.name.in_(list(rows)))}
        tags = {i.name: i for i in session.query(Tag).filter(Tag.name.in_(list(_playlist_tag_names(rows.values()))))}
        for name, row in rows.items():
            if not (collection := existing.get(name)):
                collection = Collection(name=name, kind='playlist')
                session.add(collection)
            collection.description = row['description']
            collection.directory = (get_media_directory() / row['directory']) if row['directory'] else None
            collection.tag = tags.get(row['tag_name'])
        session.flush()

    def delete(self, session: Session, keys: Set[str]):
        from .models import Collection
        for collection in session.query(Collection).filter(Collection.kind == 'playlist',
                                                           Collection.name.in_(list(keys))):
            logger.info(f'Deleting playlist {collection.name!r} (no longer in config)')
            session.delete(collection)


class PlaylistItemsSection(ConfigSection):
    """playlists.yaml's playlist items, keyed by (playlist name, kind, reference, Zim entry): a file's or Zim's
    media-relative path, or a URL.  A playlist has at most one item per reference (CollectionItem's constraints), so
    moving an item changes only its position, and it keeps its row."""
    name = 'items'

    @staticmethod
    def item_key(name: str, data: dict) -> Optional[tuple]:
        if not isinstance(data, dict):
            raise ValueError('An item must be a mapping')
        if 'file' in data:
            return name, 'file', media_relative(data['file']), None
        elif 'zim' in data:
            if not data.get('entry') or not isinstance(data['entry'], str):
                raise ValueError('A zim item requires an entry')
            return name, 'zim', media_relative(data['zim']), data['entry']
        elif 'url' in data:
            if not isinstance(data['url'], str):
                raise ValueError('An item\'s url must be text')
            return name, 'url', data['url'], None
        raise ValueError('An item requires a file, zim, or url')

    def file_rows(self, config: dict) -> Tuple[Dict[tuple, dict], Set[tuple]]:
        rows, invalid = dict(), set()
        for data in config.get('playlists') or []:
            if not (name := _playlist_name(data)):
                continue
            items = data.get('items') or []
            if not isinstance(items, list):
                logger.error(f'Skipping the items of playlist {name!r}, they are not a list: {items!r}')
                invalid.add((name, None, ITEMS_UNREADABLE, None))
                continue
            # Positions follow the file's order; an item skipped now keeps its place for a later import.
            for position, item in enumerate(items, start=1):
                try:
                    key = self.item_key(name, item)
                except Exception as e:
                    logger.error(f'Skipping invalid item of playlist {name!r}: {item}', exc_info=e)
                    key = None
                if key is None or key in rows:
                    if key:
                        logger.warning(f'Skipping duplicate item of playlist {name!r}: {item}')
                    # Counted as skipped (the config is not saved over it); a kind of None is never an item's key.
                    invalid.add((name, None, position, None))
                    continue
                rows[key] = dict(position=position, title=item.get('title'))
        return rows, invalid

    def present(self, config: dict, file_rows: dict, invalid_keys: set) -> bool:
        # A listed playlist without items has none: only an empty or missing playlists list removes nothing.
        return any(map(_playlist_name, config.get('playlists') or []))

    @staticmethod
    def _query(session: Session, *columns):
        from modules.zim.models import Zim
        from wrolpi.files.models import FileGroup
        from .models import Collection, CollectionItem
        return session.query(*columns, Collection.name, CollectionItem.item_kind, FileGroup.primary_path, Zim.path,
                             CollectionItem.zim_entry, CollectionItem.url) \
            .join(Collection, Collection.id == CollectionItem.collection_id) \
            .outerjoin(FileGroup, FileGroup.id == CollectionItem.file_group_id) \
            .outerjoin(Zim, Zim.id == CollectionItem.zim_id) \
            .filter(Collection.kind == 'playlist')

    @staticmethod
    def _db_key(name, item_kind, primary_path, zim_path, zim_entry, url) -> Optional[tuple]:
        if item_kind == 'file' and primary_path:
            return name, 'file', media_relative(primary_path), None
        elif item_kind == 'zim' and zim_path:
            return name, 'zim', media_relative(zim_path), zim_entry
        elif item_kind == 'url':
            return name, 'url', url, None
        # Not saved (see `CollectionItem.to_config`), so never "removed".
        return None

    def db_rows(self, session: Session) -> Dict[tuple, dict]:
        from .models import CollectionItem
        rows = dict()
        for position, title, *values in self._query(session, CollectionItem.position, CollectionItem.title):
            if key := self._db_key(*values):
                rows[key] = dict(position=position, title=title)
        return rows

    def upsert(self, session: Session, rows: Dict[tuple, dict]):
        from modules.zim.models import Zim
        from wrolpi.files.models import FileGroup
        from .models import Collection, CollectionItem
        media_directory = get_media_directory()
        collection_ids = dict(session.query(Collection.name, Collection.id).filter(
            Collection.kind == 'playlist', Collection.name.in_(list({i[0] for i in rows}))))
        file_group_ids = dict()
        for paths in chunks({str(media_directory / i[2]) for i in rows if i[1] == 'file'}):
            file_group_ids.update((media_relative(path), id_) for path, id_ in
                                  session.query(FileGroup.primary_path, FileGroup.id)
                                  .filter(FileGroup.primary_path.in_(paths)))
        zim_ids = {media_relative(path): id_ for id_, path in session.query(Zim.id, Zim.path)} \
            if any(i[1] == 'zim' for i in rows) else dict()
        existing = {(i.collection_id, i.item_kind, i.file_group_id, i.zim_id, i.zim_entry, i.url): i for i in
                    session.query(CollectionItem).filter(CollectionItem.collection_id.in_(collection_ids.values()))}

        new = list()
        for key, row in rows.items():
            name, kind, reference, zim_entry = key
            values = dict(collection_id=collection_ids.get(name), item_kind=kind, file_group_id=None, zim_id=None,
                          zim_entry=None, url=None)
            if kind == 'file':
                values['file_group_id'] = file_group_ids.get(reference)
            elif kind == 'zim':
                values.update(zim_id=zim_ids.get(reference), zim_entry=zim_entry)
            else:
                values['url'] = reference
            if not values['collection_id'] or (kind == 'file' and not values['file_group_id']) \
                    or (kind == 'zim' and not values['zim_id']):
                logger.warning(f'Playlist {name!r}: cannot find {reference!r}, skipping')
                continue
            if item := existing.get(tuple(values.values())):
                item.position, item.title = row['position'], row['title']
            else:
                new.append(dict(values, position=row['position'], title=row['title']))
        if new:
            # One statement for all new items (a rebuilt database has thousands).  Not flushed: count it.
            session.execute(insert(CollectionItem), new)
            count_config_change(session, PlaylistsConfig.file_name)
        session.flush()

    def delete(self, session: Session, keys: Set[tuple]):
        from .models import CollectionItem
        for item, *values in self._query(session, CollectionItem) \
                .filter(CollectionItem.collection_id.in_(self._collection_ids(session, keys))):
            if self._db_key(*values) in keys:
                session.delete(item)

    @staticmethod
    def _collection_ids(session: Session, keys) -> List[int]:
        from .models import Collection
        return [i for i, in session.query(Collection.id).filter(
            Collection.kind == 'playlist', Collection.name.in_(list({i[0] for i in keys})))]


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
    sections = (PlaylistsSection(), PlaylistItemsSection())
    validator = PlaylistsConfigValidator
    default_config = dict(version=0, playlists=[])
    width = 120

    @property
    def playlists(self) -> List[dict]:
        return self._config.get('playlists', [])

    def prepare(self, diffs: dict):
        self._drop_unknown_tags(diffs['playlists'])
        self._drop_missing_items(diffs['items'])
        self._keep_unreadable_items(diffs['items'])
        if not self.import_deletes:
            self._merge_items(diffs['items'])

    def _drop_unknown_tags(self, diff: SectionDiff):
        """A Tag that no longer exists (it was removed) is dropped, and the config is saved without it.  Only once
        tags.yaml was imported; until then its Tags may be missing."""
        from wrolpi.tags import Tag, get_tags_config
        rows = [*diff.added.values(), *diff.changed.values()]
        if not (names := _playlist_tag_names(rows)) or not get_tags_config().successful_import:
            return
        with get_db_session() as session:
            unknown = names - {i for i, in session.query(Tag.name).filter(Tag.name.in_(list(names)))}
        for row in rows:
            if row['tag_name'] in unknown:
                logger.warning(f'Removing unknown Tag {row["tag_name"]!r} from a playlist')
                row['tag_name'] = None
                self._config_outdated = True

    def _keep_unreadable_items(self, diff: SectionDiff):
        """A playlist whose items cannot be read keeps the items it has."""
        _, invalid = PlaylistItemsSection().file_rows(self.import_file_config)
        if names := {i[0] for i in invalid if i[2] == ITEMS_UNREADABLE}:
            diff.removed = {i for i in diff.removed if i[0] not in names}

    def _drop_missing_items(self, diff: SectionDiff):
        """An added item whose file or Zim is not in the database (not indexed yet, after a rebuild) is skipped
        before the write; a later import (after the refresh) adds it."""
        from modules.zim.models import Zim
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        files = {i[2] for i in diff.added if i[1] == 'file'}
        zims = {i[2] for i in diff.added if i[1] == 'zim'}
        known = set()
        with get_db_session() as session:
            for paths in chunks({str(media_directory / i) for i in files}):
                known.update(('file', media_relative(i)) for i, in
                             session.query(FileGroup.primary_path).filter(FileGroup.primary_path.in_(paths)))
            if zims:
                known.update(('zim', media_relative(i)) for i, in session.query(Zim.path))
        for key in list(diff.added):
            if key[1] in ('file', 'zim') and (key[1], key[2]) not in known:
                logger.warning(f'Playlist {key[0]!r}: {key[1]} not indexed, skipping {key[2]!r}')
                del diff.added[key]
                self.import_skipped += 1

    def _merge_items(self, diff: SectionDiff):
        """Without deletes, a playlist's items in the database keep their order, and the file's other items are
        added after the item that precedes them in the file.  Only titles are taken from the file's other items."""
        section = PlaylistItemsSection()
        if not (names := {i[0] for i in (*diff.added, *diff.changed)}):
            return
        with get_db_session() as session:
            db_rows = section.db_rows(session)
        file_rows, _ = section.file_rows(self.import_file_config)
        for name in names:
            merged = sorted((i for i in db_rows if i[0] == name), key=lambda i: db_rows[i]['position'])
            previous = None
            for key in sorted((i for i in file_rows if i[0] == name), key=lambda i: file_rows[i]['position']):
                if key in db_rows:
                    previous = key
                elif key in diff.added:
                    merged.insert(merged.index(previous) + 1 if previous else 0, key)
                    previous = key
            for position, key in enumerate(merged, start=1):
                if key in diff.added:
                    diff.added[key]['position'] = position
                    continue
                row = dict(position=position, title=(diff.changed.get(key) or db_rows[key])['title'])
                if row == db_rows[key]:
                    diff.changed.pop(key, None)
                else:
                    diff.changed[key] = row

    def import_config(self, file: pathlib.Path = None, send_events=False):
        self._config_outdated = False
        super().import_config(file, send_events)

    def after_import(self, diffs: dict):
        if self._config_outdated:
            self.background_dump.activate_switch()

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

        # Importing a backup is the user's choice: apply it whatever the versions.
        self.import_forced(send_events=send_events)
        # Materialize the restored playlists on disk.
        from .sync import sync_playlists_directory
        sync_playlists_directory.activate_switch()

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        """Dump all playlists (with their ordered items) to the config file."""
        from .models import Collection

        with get_db_session() as session:
            # The database's version (see wrolpi.config_version); it is never older than a file it saved.
            version = self.db_version_for_dump(session)
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
            self._config['version'] = version

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


def file_groups_moved(session, file_group_ids):
    """Call after FileGroups change path (rename/move/reorganize).

    playlists.yaml references file items by path, so it must be re-saved (and the playlist
    directories re-synced) or the next import will not find the file and will drop the item.
    tags.yaml and recently_viewed.yaml save files by path too.  The move (often raw SQL) is counted as each config's
    change.

    `file_group_ids` may be an iterable of ids or a select of ids."""
    from wrolpi.files.models import FileGroup
    from .models import Collection, CollectionItem

    if session.query(TagFile.file_group_id).filter(TagFile.file_group_id.in_(file_group_ids)).first():
        count_config_change(session, TagsConfig.file_name)
        save_tags_config.activate_switch()

    in_playlist = session.query(CollectionItem.id) \
        .join(Collection, Collection.id == CollectionItem.collection_id) \
        .filter(Collection.kind == 'playlist', CollectionItem.file_group_id.in_(file_group_ids)) \
        .first()
    if session.query(FileGroup.id).filter(FileGroup.id.in_(file_group_ids), FileGroup.viewed.isnot(None)).first():
        count_config_change(session, RecentlyViewedConfig.file_name)
        save_recently_viewed_config.activate_switch()

    if in_playlist:
        count_config_change(session, PlaylistsConfig.file_name)
        save_playlists_config.activate_switch()
        from .sync import sync_playlists_directory
        sync_playlists_directory.activate_switch()


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
