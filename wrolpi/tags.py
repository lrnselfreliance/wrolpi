import contextlib
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Union, Set

import cachetools
import pytz
from cachetools.keys import hashkey
from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger, event, UniqueConstraint, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, relationship, Session, load_only

from wrolpi import dates, flags
from wrolpi.common import loaded, ModelHelper, Base, logger, ConfigFile, get_media_directory, background_task, \
    get_relative_to_media_directory, is_valid_hex_color, walk, INVALID_FILE_CHARS, get_wrolpi_config
from wrolpi.config_import import ConfigSection, SectionDiff, Unreadable, chunks, media_relative
from wrolpi.config_version import count_config_change, register_ownership
from wrolpi.dates import TZDateTime
from wrolpi.db import get_db_session, named_placeholders, session_curs, serializer
from wrolpi.downloader import save_downloads_config
from wrolpi.errors import UnknownTag, UsedTag, InvalidTag, FileWorkerConflict, NoPrimaryFile, InvalidConfig
from wrolpi.events import Events
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


def get_tags_directory() -> pathlib.Path:
    return get_media_directory() / 'tags'


class TagFile(ModelHelper, Base):
    __tablename__ = 'tag_file'
    __table_args__ = (
        UniqueConstraint('tag_id', 'file_group_id', name='tag_file_tag_id_file_group_id_key'),
    )
    created_at: Mapped[datetime] = Column(TZDateTime, default=dates.now)

    tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
    # Joined: a TagFile is loaded for its Tag's name (serializers, the tags config).
    tag = relationship('Tag', back_populates='tag_files', lazy='joined')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), primary_key=True)
    file_group = relationship('FileGroup', back_populates='tag_files')

    def __repr__(self):
        tag = loaded(self, 'tag', 'name') or loaded(self, 'tag_id')
        file_group = loaded(self, 'file_group', 'primary_path') or loaded(self, 'file_group_id')
        return f'<TagFile tag={tag} file_group={file_group}>'

    @staticmethod
    def get_by_primary_keys(session: Session, file_group_id: int, tag_id: int) -> Optional['TagFile']:
        return session.query(TagFile).filter_by(tag_id=tag_id, file_group_id=file_group_id).one_or_none()


# Tag.get_id_by_name
def get_id_by_name_key(klass: Base, session: Session, name: str):
    return hashkey(name)


get_id_by_name_cache = cachetools.LRUCache(maxsize=1_000)


# Tag.get_name_by_id
def get_name_by_id_key(klass: Base, session: Session, id_: int):
    return hashkey(id_)


get_name_by_id_cache = cachetools.LRUCache(maxsize=1_000)


class Tag(ModelHelper, Base):
    __tablename__ = 'tag'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String)

    tag_files: Mapped[List[TagFile]] = relationship('TagFile', back_populates='tag', cascade='all')
    tag_zim_entries: Mapped[List['TagZimEntry']] = relationship('TagZimEntry', back_populates='tag', cascade='all')

    # Note: Channel relationship removed - Channels now access Tags through Collection

    def __repr__(self):
        name = loaded(self, 'name')
        color = loaded(self, 'color')
        return f'<Tag {name=} {color=}>'

    @serializer
    def __json__(self) -> dict:
        return dict(
            id=self.id,
            name=self.name,
            color=self.color,
        )

    @classmethod
    @cachetools.cached(cache=get_id_by_name_cache, key=get_id_by_name_key)
    def get_id_by_name(cls, session: Session, name: str) -> int:
        """Returns a Tag's ID, if a Tag matches the provided name.

        @raise UnknownTag: If no Tag matches the provided name."""
        if tag := session.query(Tag).filter_by(name=name).one_or_none():
            return tag.id
        raise UnknownTag(f'No Tag with name={name}')

    @classmethod
    def invalidate_cache(cls):
        get_id_by_name_cache.clear()
        get_name_by_id_cache.clear()

    @staticmethod
    def get_by_name(session: Session, name: str) -> Optional['Tag']:
        tag = session.query(Tag).filter_by(name=name).one_or_none()
        return tag

    @staticmethod
    def find_by_name(session: Session, name: str) -> 'Tag':
        if tag := Tag.get_by_name(session, name):
            return tag

        raise UnknownTag(f'No Tag with name={name}')

    @staticmethod
    def get_by_id(session: Session, id_: int) -> Optional['Tag']:
        tag = session.query(Tag).filter_by(id=id_).one_or_none()
        return tag

    @staticmethod
    def find_by_id(session: Session, id_: int) -> 'Tag':
        if tag := Tag.get_by_id(session, id_):
            return tag

        raise UnknownTag(f'No Tag with id={id_}')

    def has_relations(self) -> bool:
        """Returns True if this Tag has been used with any FileGroups, Zim Entries, or Collections."""
        from wrolpi.collections import Collection
        session = Session.object_session(self)
        # Check if tag is used by any collection (domain or channel)
        has_collections = session.query(Collection).filter(Collection.tag_id == self.id).first() is not None
        return bool(any(self.tag_files) or any(self.tag_zim_entries) or has_collections)

    async def update_tag(self, session: Session, name: str, color: str | None):
        """Change name/color of tag.  Ensures safeness of new values, checks for conflicts."""
        if ',' in name:
            raise InvalidTag('Tag name cannot have comma')
        if color and not is_valid_hex_color(color):
            raise InvalidTag('Tag color is invalid')

        # Replace forward-slash (linux directories) with Unicode Big Solidus (U+29F8)
        name = name.replace('/', '⧸')
        name = INVALID_FILE_CHARS.sub('', name).strip()
        if not name:
            raise InvalidTag('Tag name cannot be empty')

        if (other := self.get_by_name(session, name)) and other.id != self.id:
            raise InvalidTag('Tag name already taken')

        if flags.file_worker_busy.is_set():
            raise FileWorkerConflict('Refusing to rename tag while FileWorker is busy')

        old_name = self.name
        self.name = name
        self.color = color or self.color
        if Session.object_session(self):
            self.flush()

        # Rename old name referenced in any Downloads, in the caller's transaction.  (A background task's writes
        # would not be committed with it.)  The caller saves the Downloads config after it commits.
        if old_name and old_name != name:
            from wrolpi.downloader import Download
            to_flush = list()
            downloads = session.query(Download).options(
                load_only(Download.id, Download.tag_names, Download.settings))
            for download in downloads:
                tag_names, settings = with_tag_name_renamed(download.tag_names, download.settings, old_name, name)
                if tag_names != download.tag_names or settings != download.settings:
                    download.tag_names, download.settings = tag_names, settings
                    to_flush.append(download)
            if to_flush:
                session.flush(to_flush)

        from modules.videos.errors import ChannelDirectoryConflict

        async def _():
            # Only move channels if tag is being renamed (not created)
            if old_name:
                # Get channels through Collections
                from modules.videos.models import Channel
                from wrolpi.collections import Collection
                channels = session.query(Channel).join(Collection).filter(
                    Collection.tag_id == self.id,
                    Collection.kind == 'channel'
                ).all()
                for channel in channels:
                    channel: Channel
                    possible_directory = channel.format_directory(old_name)
                    if channel.directory == possible_directory:
                        # Channel is in this Tag's old directory, move the Channel to the new directory.
                        new_directory = channel.format_directory(name)
                        try:
                            new_directory.mkdir(parents=True)
                        except FileExistsError:
                            raise ChannelDirectoryConflict(f'Channel directory already exists: {new_directory}')

                        # Move the files of the Channel.
                        await channel.move_channel(new_directory, session)
                    else:
                        msg = f"Not moving Channel because it is not in this Tag's old directory:" \
                              f" {channel} {possible_directory} {self}"
                        logger.warning(msg)

        background_task(_())

    def delete(self):
        """Deletes this Tag, if it is unused.

        @warning: Commits and saves configs"""
        if self.has_relations():
            raise UsedTag(f'Cannot delete {self.name} it is used')

        name = self.name

        session = Session.object_session(self)
        session.delete(self)

        # Remove any Download references.
        from wrolpi.downloader import Download
        to_flush = list()
        for download in session.query(Download):
            if download.tag_names:
                download.tag_names = [i for i in download.tag_names if i != name]
                to_flush.append(download)
        if to_flush:
            session.flush(to_flush)
            save_downloads_config.activate_switch()

        session.commit()

        save_tags_config.activate_switch()
        sync_tags_directory.activate_switch()

    @staticmethod
    def get_or_create_tag(session: Session, name: str = None, id_: int = None) -> 'Tag':
        """Gets or creates Tag object.

        @warning: does not commit"""
        if name and id_:
            raise RuntimeError('Tag name and id cannot be used together')
        name = name.strip() if name else name

        if tag := session.query(Tag).filter(Tag.id == id_).one_or_none():
            return tag
        if tag := session.query(Tag).filter(Tag.name == name).one_or_none():
            return tag

        if not name:
            raise InvalidTag('Tag name cannot be empty')

        tag = Tag(name=name)
        session.add(tag)
        # Flush so the new Tag has an id (callers use `.id` immediately).
        tag.flush(session)
        return tag


@event.listens_for(Tag, 'after_insert')
@event.listens_for(Tag, 'after_update')
@event.listens_for(Tag, 'after_delete')
def invalidate_cache(mapper, connection, target):
    """Clear Tag cache when Tags are changed."""
    Tag.invalidate_cache()


@dataclass
class TagsConfigValidator:
    tag_files: list[list] = field(default_factory=list)
    tag_zims: list[list] = field(default_factory=list)
    tags: dict = field(default_factory=dict)
    version: int = None


def _utc_or_none(value) -> Optional[datetime]:
    """A config's date (an ISO string, or a datetime YAML parsed) or the database's, in UTC."""
    if not value:
        return None
    if isinstance(value, str):
        return dates.strptime_ms(value)
    return value.astimezone(pytz.UTC) if value.tzinfo else value.replace(tzinfo=pytz.UTC)


def without_tag_names(download_tag_names: Optional[List[str]], settings: Optional[dict], names: Set[str]) \
        -> Tuple[Optional[List[str]], Optional[dict]]:
    """A Download's tag_names and settings without these Tag names, in the settings' tag_names and channel_tag_name
    (passed on to the Downloads and Channels it creates) too.  New objects, so an ORM change to the JSON is seen."""
    if download_tag_names:
        download_tag_names = [i for i in download_tag_names if i not in names]
    if settings:
        settings = {key: [i for i in value if i not in names] if key in ('tag_names', 'channel_tag_name') and value
                    else value for key, value in settings.items()}
    return download_tag_names, settings


def with_tag_name_renamed(download_tag_names: Optional[List[str]], settings: Optional[dict], old_name: str,
                          new_name: str) -> Tuple[Optional[List[str]], Optional[dict]]:
    """A Download's tag_names and settings with a Tag's old name replaced, in the settings' tag_names and
    channel_tag_name too.  New objects, so an ORM change to the JSON is seen."""
    if download_tag_names:
        download_tag_names = [new_name if i == old_name else i for i in download_tag_names]
    if settings:
        settings = {key: [new_name if i == old_name else i for i in value]
                    if key in ('tag_names', 'channel_tag_name') and value else value
                    for key, value in settings.items()}
    return download_tag_names, settings


def remove_tag_names_from_downloads(session: Session, names: Set[str]):
    """Remove these Tag names from every Download that would apply them; applying a Tag that does not exist fails
    the download.  (Changes download_manager.yaml.)"""
    from wrolpi.downloader import Download
    changed = False
    for download in session.query(Download).options(load_only(Download.id, Download.tag_names, Download.settings)):
        tag_names, settings = without_tag_names(download.tag_names, download.settings, names)
        if tag_names != download.tag_names or settings != download.settings:
            download.tag_names, download.settings = tag_names, settings
            changed = True
    if changed:
        save_downloads_config.activate_switch()


def unknown_tag_names(names: Set[str]) -> Set[str]:
    """The names no Tag has (the Tag was removed).  None until tags.yaml was imported: its Tags may be missing."""
    if not names or not get_tags_config().successful_import:
        return set()
    with get_db_session() as session:
        return names - {i for i, in session.query(Tag.name).filter(Tag.name.in_(list(names)))}


def _tag_ids(session: Session, names) -> Dict[str, int]:
    tag_ids = dict()
    for chunk in chunks(names):
        tag_ids.update(session.query(Tag.name, Tag.id).filter(Tag.name.in_(chunk)))
    return tag_ids


class TagsSection(ConfigSection):
    """tags.yaml's Tags, keyed by name."""
    name = 'tags'

    def file_rows(self, config: dict) -> Tuple[Dict[str, dict], Set[str]]:
        rows, invalid = dict(), set()
        for name, attrs in (config.get('tags') or dict()).items():
            try:
                rows[name] = dict(color=attrs.get('color'))
            except Exception as e:
                logger.error(f'Skipping invalid Tag in config: {name}', exc_info=e)
                invalid.add(name)
        return rows, invalid

    def db_rows(self, session: Session) -> Dict[str, dict]:
        return {name: dict(color=color) for name, color in session.query(Tag.name, Tag.color)}

    def upsert(self, session: Session, rows: Dict[str, dict]):
        existing = {i.name: i for i in session.query(Tag).filter(Tag.name.in_(list(rows)))}
        for name, row in rows.items():
            if tag := existing.get(name):
                tag.color = row['color']
            else:
                logger.info(f'Creating Tag {repr(name)}')
                session.add(Tag(name=name, color=row['color']))
        session.flush()

    def delete(self, session: Session, keys: Set[str]):
        """A removed Tag is deleted with its tagged files and Zim entries.  A Collection using it keeps its
        directory, and loses only the Tag (its config is then saved)."""
        from wrolpi.collections import Collection
        remove_tag_names_from_downloads(session, set(keys))
        for tag in session.query(Tag).filter(Tag.name.in_(list(keys))):
            for collection in session.query(Collection).filter(Collection.tag_id == tag.id):
                logger.warning(f'Removing Tag {repr(tag.name)} from {collection}')
                collection.tag = None
                collection.tag_id = None
            logger.warning(f'Deleting {tag} because it is not in the config')
            session.delete(tag)


class TagFilesSection(ConfigSection):
    """tags.yaml's tagged files, keyed by (Tag name, the FileGroup's primary path relative to the media
    directory).  A tagged file whose Tag the config does not list is skipped (no FileGroup is created for it)."""
    name = 'tag_files'

    def file_rows(self, config: dict) -> Tuple[Dict[tuple, dict], Set[tuple]]:
        tag_names = set(config.get('tags') or dict())
        rows, invalid = dict(), set()
        for position, item in enumerate(config.get('tag_files') or []):
            try:
                tag_name, path, *rest = item if isinstance(item, list) else ()
                if not isinstance(tag_name, str):
                    raise ValueError('A Tag name must be text')
                key = (tag_name, media_relative(path))
            except Exception as e:
                logger.error(f'Skipping invalid tagged file in config: {item!r}', exc_info=e)
                # Counted as skipped (see `Unreadable`).
                invalid.add(Unreadable(position))
                continue
            if tag_names and tag_name not in tag_names:
                logger.warning(f'Cannot find Tag for {repr(key[1])}')
                invalid.add(key)
                continue
            try:
                rows[key] = dict(created_at=_utc_or_none(rest[0] if rest else None))
            except Exception as e:
                logger.error(f'Skipping invalid tagged file in config: {item}', exc_info=e)
                invalid.add(key)
        return rows, invalid

    def db_rows(self, session: Session) -> Dict[tuple, dict]:
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        query = session.query(Tag.name, FileGroup.primary_path, TagFile.created_at) \
            .join(TagFile, TagFile.tag_id == Tag.id) \
            .join(FileGroup, FileGroup.id == TagFile.file_group_id)
        return {(name, str(primary_path.relative_to(media_directory))): dict(created_at=_utc_or_none(created_at))
                for name, primary_path, created_at in query}

    def same(self, file_row: dict, db_row: dict) -> bool:
        # A tagged file without a date keeps the database's.
        return file_row['created_at'] is None or file_row == db_row

    def upsert(self, session: Session, rows: Dict[tuple, dict]):
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        tag_ids = _tag_ids(session, {tag_name for tag_name, _ in rows})
        paths = {key: str(media_directory / key[1]) for key in rows}
        file_group_ids = dict()
        for chunk in chunks(set(paths.values())):
            file_group_ids.update((str(path), id_) for path, id_ in
                                  session.query(FileGroup.primary_path, FileGroup.id)
                                  .filter(FileGroup.primary_path.in_(chunk)))

        # FileGroups for files found on disk by `prepare`, flushed together.  Every member path is cached, so a
        # group named by two of its files is created once.
        new_groups = dict()
        with session.no_autoflush:
            for key, row in rows.items():
                if not row.get('files') or paths[key] in file_group_ids or paths[key] in new_groups:
                    continue
                file_group = FileGroup.from_paths(session, *row['files'])
                for member in row['files']:
                    new_groups[str(member)] = file_group
        if new_groups:
            session.flush(list({id(i): i for i in new_groups.values()}.values()))
            file_group_ids.update({path: file_group.id for path, file_group in new_groups.items()})

        existing = dict()
        for chunk in chunks(set(file_group_ids.values())):
            existing.update({(i.tag_id, i.file_group_id): i for i in
                             session.query(TagFile).filter(TagFile.file_group_id.in_(chunk))})
        new = dict()
        for key, row in rows.items():
            tag_id, file_group_id = tag_ids.get(key[0]), file_group_ids.get(paths[key])
            if not tag_id or not file_group_id:
                logger.warning(f'Cannot tag {repr(key[1])} with {repr(key[0])}')
                continue
            if tag_file := existing.get((tag_id, file_group_id)):
                if row['created_at']:
                    tag_file.created_at = row['created_at']
            else:
                new[(tag_id, file_group_id)] = dict(tag_id=tag_id, file_group_id=file_group_id,
                                                    created_at=row['created_at'] or dates.now())
        if new:
            # One statement for all new TagFiles.  Not flushed: count it.
            session.execute(insert(TagFile), list(new.values()))
            count_config_change(session, TagsConfig.file_name)
        session.flush()

    def delete(self, session: Session, keys: Set[tuple]):
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        for chunk in chunks(keys):
            chunk = set(chunk)
            query = session.query(TagFile, Tag.name, FileGroup.primary_path) \
                .join(Tag, Tag.id == TagFile.tag_id) \
                .join(FileGroup, FileGroup.id == TagFile.file_group_id) \
                .filter(FileGroup.primary_path.in_({str(media_directory / path) for _, path in chunk}))
            for tag_file, name, primary_path in query:
                if (name, str(primary_path.relative_to(media_directory))) in chunk:
                    session.delete(tag_file)


class TagZimsSection(ConfigSection):
    """tags.yaml's tagged Zim entries, keyed by (Tag name, Zim path relative to the media directory, entry)."""
    name = 'tag_zims'

    def file_rows(self, config: dict) -> Tuple[Dict[tuple, dict], Set[tuple]]:
        tag_names = set(config.get('tags') or dict())
        rows, invalid = dict(), set()
        for position, item in enumerate(config.get('tag_zims') or []):
            try:
                tag_name, zim_path, zim_entry, *rest = item if isinstance(item, list) else ()
                if not isinstance(tag_name, str) or not isinstance(zim_entry, str):
                    raise ValueError('A Tag name and a Zim entry must be text')
                key = (tag_name, media_relative(zim_path), zim_entry)
            except Exception as e:
                logger.error(f'Skipping invalid tagged Zim entry in config: {item!r}', exc_info=e)
                # Counted as skipped (see `Unreadable`).
                invalid.add(Unreadable(position))
                continue
            if tag_names and tag_name not in tag_names:
                logger.warning(f'Cannot find Tag for {repr(key[1])}')
                invalid.add(key)
                continue
            try:
                rows[key] = dict(created_at=_utc_or_none(rest[0] if rest else None))
            except Exception as e:
                logger.error(f'Skipping invalid tagged Zim entry in config: {item}', exc_info=e)
                invalid.add(key)
        return rows, invalid

    def db_rows(self, session: Session) -> Dict[tuple, dict]:
        from modules.zim.models import TagZimEntry, Zim
        media_directory = get_media_directory()
        query = session.query(Tag.name, Zim.path, TagZimEntry.zim_entry, TagZimEntry.created_at) \
            .join(TagZimEntry, TagZimEntry.tag_id == Tag.id) \
            .join(Zim, Zim.id == TagZimEntry.zim_id)
        return {(name, str(path.relative_to(media_directory)), zim_entry): dict(created_at=_utc_or_none(created_at))
                for name, path, zim_entry, created_at in query}

    def same(self, file_row: dict, db_row: dict) -> bool:
        return file_row['created_at'] is None or file_row == db_row

    def upsert(self, session: Session, rows: Dict[tuple, dict]):
        from modules.zim.models import TagZimEntry, Zim
        media_directory = get_media_directory()
        tag_ids = _tag_ids(session, {tag_name for tag_name, _, _ in rows})
        zim_ids = {str(path.relative_to(media_directory)): id_ for id_, path in session.query(Zim.id, Zim.path)}
        existing = {(i.tag_id, i.zim_id, i.zim_entry): i for i in
                    session.query(TagZimEntry).filter(TagZimEntry.tag_id.in_(list(tag_ids.values())))}
        new = dict()
        for (tag_name, zim_path, zim_entry), row in rows.items():
            tag_id, zim_id = tag_ids.get(tag_name), zim_ids.get(zim_path)
            if not tag_id or not zim_id:
                logger.warning(f'Cannot tag {repr(zim_entry)} of {repr(zim_path)} with {repr(tag_name)}')
                continue
            if tag_zim_entry := existing.get((tag_id, zim_id, zim_entry)):
                if row['created_at']:
                    tag_zim_entry.created_at = row['created_at']
            else:
                new[(tag_id, zim_id, zim_entry)] = dict(tag_id=tag_id, zim_id=zim_id, zim_entry=zim_entry,
                                                        created_at=row['created_at'] or dates.now())
        if new:
            # Not flushed: count it.
            session.execute(insert(TagZimEntry), list(new.values()))
            count_config_change(session, TagsConfig.file_name)
        session.flush()

    def delete(self, session: Session, keys: Set[tuple]):
        from modules.zim.models import TagZimEntry, Zim
        media_directory = get_media_directory()
        query = session.query(TagZimEntry, Tag.name, Zim.path) \
            .join(Tag, Tag.id == TagZimEntry.tag_id) \
            .join(Zim, Zim.id == TagZimEntry.zim_id) \
            .filter(Tag.name.in_({tag_name for tag_name, _, _ in keys}))
        for tag_zim_entry, name, path in query:
            if (name, str(path.relative_to(media_directory)), tag_zim_entry.zim_entry) in keys:
                session.delete(tag_zim_entry)


class TagsConfig(ConfigFile):
    file_name = 'tags.yaml'
    sections = (TagsSection(), TagFilesSection(), TagZimsSection())
    width = 500
    validator = TagsConfigValidator
    default_config = dict(
        tag_files=list(),
        tag_zims=list(),
        tags=dict(),
        version=0,
    )

    @property
    def tag_files(self) -> list:
        return self._config['tag_files']

    @tag_files.setter
    def tag_files(self, value):
        value = sorted(value, key=lambda i: (i[0].lower(), i[1]))
        self.update({'tag_files': value})

    @property
    def tag_zims(self) -> list:
        return self._config['tag_zims']

    @tag_zims.setter
    def tag_zims(self, value):
        value = sorted(value, key=lambda i: (i[0].lower(), i[1], i[2]))
        self.update({'tag_zims': value})

    @property
    def tags(self) -> dict:
        return self._config['tags']

    @tags.setter
    def tags(self, value: dict):
        self.update({'tags': value})

    def dump_config(self, file: pathlib.Path = None, send_events=False, overwrite=False):
        try:
            media_directory = get_media_directory()

            with get_db_session() as session:
                version = self.db_version_for_dump(session)
                tags = dict()
                tag_rows = session.query(Tag)
                for tag in tag_rows:
                    tags[tag.name] = dict(color=tag.color)

                from wrolpi.files.models import FileGroup
                results = session.query(Tag, TagFile, FileGroup) \
                    .filter(TagFile.tag_id == Tag.id, TagFile.file_group_id == FileGroup.id) \
                    .order_by(FileGroup.primary_path)

                tag_files = []
                for tag, tag_file, file_group in results:
                    value = [
                        tag.name,
                        str(file_group.primary_path.relative_to(media_directory)),
                        # Fallback to current time if not set.
                        tag_file.created_at.isoformat() if tag_file.created_at else dates.now().isoformat(),
                    ]
                    tag_files.append(value)
                logger.debug(f'Got {len(tag_files)} tag files for config.')

                from modules.zim.models import Zim, TagZimEntry
                results = session.query(Tag, Zim, TagZimEntry) \
                    .filter(Tag.id == TagZimEntry.tag_id, Zim.id == TagZimEntry.zim_id) \
                    .order_by(TagZimEntry.zim_id, TagZimEntry.zim_entry)

                tag_zims = []
                for tag, zim, tag_zim_entry in results:
                    zim: Zim
                    tag_zim_entry: TagZimEntry
                    value = [
                        tag.name,
                        str(get_relative_to_media_directory(zim.path)),
                        tag_zim_entry.zim_entry,
                        # Fallback to current time if not set.
                        tag_zim_entry.created_at.isoformat() if tag_zim_entry.created_at else dates.now().isoformat(),
                    ]
                    tag_zims.append(value)
                logger.debug(f'Got {len(tag_zims)} tag zims for config.')

                # Write to the config.
                self.update({
                    'tag_files': tag_files,
                    'tag_zims': tag_zims,
                    'tags': tags,
                    'version': version,
                })
        except Exception as e:
            message = f'Failed to save {self.get_relative_file()} config'
            logger.error(message, exc_info=e)
            if send_events:
                Events.send_config_save_failed(message)

    def import_config(self, file: pathlib.Path = None, send_events=False):
        if PYTEST and not TEST_TAGS_CONFIG:
            logger.warning('Refusing to import tags without test tags config.  '
                           'Use `test_tags_config` fixture if you would like to call this.')
            return

        self._config_outdated = False
        super().import_config(file, send_events)

    def prepare(self, diffs: dict):
        self._prepare_tag_files(diffs['tag_files'])
        self._prepare_tag_zims(diffs['tag_zims'])

    def _prepare_tag_files(self, diff: SectionDiff):
        """Find the files of added tagged files that have no FileGroup yet (a rebuilt database), so `upsert` can
        create them.  A file that is neither in the database nor on disk is skipped.  A file named by one of its
        group's other files (an old config) tags the group's primary file."""
        from wrolpi.files.lib import choose_primary_file, split_path_stem_and_suffix
        from wrolpi.files.models import FileGroup
        media_directory = get_media_directory()
        known = set()
        with get_db_session() as session:
            for paths in chunks({str(media_directory / path) for _, path in diff.added}):
                known.update(str(i) for i, in
                             session.query(FileGroup.primary_path).filter(FileGroup.primary_path.in_(paths)))

        listings: Dict[pathlib.Path, List[pathlib.Path]] = dict()
        for key, row in list(diff.added.items()):
            tag_name, path = key
            absolute = media_directory / path
            if str(absolute) in known:
                continue
            del diff.added[key]
            if not absolute.is_file():
                logger.warning(f'Cannot find FileGroup for {repr(path)}')
                self.import_skipped += 1
                continue
            # Each directory is listed once (a Channel's directory can hold thousands of files).
            if absolute.parent not in listings:
                listings[absolute.parent] = list(absolute.parent.iterdir())
            stem, _ = split_path_stem_and_suffix(absolute)
            files = [i for i in listings[absolute.parent] if i == absolute or i.name.startswith(f'{stem}.')]
            try:
                primary = choose_primary_file(files)
            except NoPrimaryFile:
                logger.error(f'Failed to tag {absolute}')
                self.import_skipped += 1
                continue
            primary_key = (tag_name, str(primary.relative_to(media_directory)))
            if primary_key != key:
                # The config is saved with the primary file.
                self._config_outdated = True
                diff.removed.discard(primary_key)
            diff.added.setdefault(primary_key, dict(row, files=files))

    def _prepare_tag_zims(self, diff: SectionDiff):
        """A Zim entry tagged in a Zim file that is gone (replaced by a newer one) moves to the newest Zim of the
        same name; one with no such Zim is skipped."""
        from modules.zim import lib as zim_lib
        from modules.zim.models import Zim
        if not diff.added:
            return
        media_directory = get_media_directory()
        with get_db_session() as session:
            zim_paths = [i for i, in session.query(Zim.path)]
        known = {str(i.relative_to(media_directory)) for i in zim_paths}
        # {name: (date, path)} of the newest Zim of each name, like `migrate_outdated_zim_tags`.
        newest = dict()
        for path in zim_paths:
            try:
                name, date = zim_lib.parse_name(path)
            except ValueError:
                continue
            if name not in newest or date > newest[name][0]:
                newest[name] = (date, path)

        for key, row in list(diff.added.items()):
            tag_name, zim_path, zim_entry = key
            if zim_path in known:
                continue
            del diff.added[key]
            try:
                name, _ = zim_lib.parse_name(media_directory / zim_path)
            except ValueError:
                name = None
            if name not in newest:
                logger.warning(f'Cannot find Zim for {repr(zim_path)}')
                self.import_skipped += 1
                continue
            new_key = (tag_name, str(newest[name][1].relative_to(media_directory)), zim_entry)
            logger.warning(f'Migrating Zim entry tag {repr(tag_name)} from {zim_path} to {new_key[1]}')
            self._config_outdated = True
            diff.removed.discard(new_key)
            diff.added.setdefault(new_key, row)

    def after_import(self, diffs: dict):
        if diffs['tags']:
            Tag.invalidate_cache()
        if self._config_outdated:
            self.background_dump.activate_switch()

    def _backup_parts(self, data: dict, file: pathlib.Path) -> Tuple[dict, list, list]:
        """The tags, tag_files and tag_zims a backup preview or merge reads (see `ConfigFile.backup_entries`)."""
        tags = data.get('tags') or dict()
        if not isinstance(tags, dict):
            raise InvalidConfig(f'{get_relative_to_media_directory(file)}: "tags" is not a mapping')
        return tags, self.backup_entries(data, 'tag_files', file, items=2), \
            self.backup_entries(data, 'tag_zims', file, items=3)

    def preview_backup_import(self, backup_date: str, mode: str) -> dict:
        backup_file = self._get_backup_file(backup_date)
        backup_data = self.read_config_file(backup_file)
        current_data = self.read_config_file() if self.get_file().is_file() else dict(tags={}, tag_files=[],
                                                                                      tag_zims=[])

        backup_tags, backup_tag_files, backup_tag_zims = self._backup_parts(backup_data, backup_file)
        current_tags, current_tag_files, current_tag_zims = self._backup_parts(current_data, self.get_file())

        # Build identity sets
        current_tag_names = set(current_tags.keys())
        current_tf_keys = {(tf[0], tf[1]) for tf in current_tag_files if len(tf) >= 2}
        current_tz_keys = {(tz[0], tz[1], tz[2]) for tz in current_tag_zims if len(tz) >= 3}

        backup_tag_names = set(backup_tags.keys())
        backup_tf_keys = {(tf[0], tf[1]) for tf in backup_tag_files if len(tf) >= 2}
        backup_tz_keys = {(tz[0], tz[1], tz[2]) for tz in backup_tag_zims if len(tz) >= 3}

        add = []
        remove = []
        unchanged = 0

        # Tags
        for name in sorted(backup_tag_names):
            if name not in current_tag_names:
                add.append(dict(type='tag', name=name))
            else:
                unchanged += 1
        if mode == 'overwrite':
            for name in sorted(current_tag_names - backup_tag_names):
                remove.append(dict(type='tag', name=name))

        # Tag files
        for tf in backup_tag_files:
            if len(tf) >= 2:
                key = (tf[0], tf[1])
                if key not in current_tf_keys:
                    add.append(dict(type='tag_file', tag=tf[0], path=tf[1]))
                else:
                    unchanged += 1
        if mode == 'overwrite':
            for key in sorted(current_tf_keys - backup_tf_keys):
                remove.append(dict(type='tag_file', tag=key[0], path=key[1]))

        # Tag zims
        for tz in backup_tag_zims:
            if len(tz) >= 3:
                key = (tz[0], tz[1], tz[2])
                if key not in current_tz_keys:
                    add.append(dict(type='tag_zim', tag=tz[0], zim=tz[1], entry=tz[2]))
                else:
                    unchanged += 1
        if mode == 'overwrite':
            for key in sorted(current_tz_keys - backup_tz_keys):
                remove.append(dict(type='tag_zim', tag=key[0], zim=key[1], entry=key[2]))

        return dict(mode=mode, add=add, remove=remove, unchanged=unchanged)

    def import_backup(self, backup_date: str, mode: str, send_events: bool = False):
        self._preserve_current_config()
        import shutil
        backup_file = self._get_backup_file(backup_date)
        config_file = self.get_file()

        if mode == 'overwrite':
            config_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, config_file)
        elif mode == 'merge':
            backup_data = self.read_config_file(backup_file)
            current_data = self.read_config_file() if config_file.is_file() else dict(tags={}, tag_files=[],
                                                                                      tag_zims=[], version=0)

            current_tags, current_tag_files, current_tag_zims = self._backup_parts(current_data, config_file)
            backup_tags, backup_tag_files, backup_tag_zims = self._backup_parts(backup_data, backup_file)

            # Merge tags: add missing tags only
            merged_tags = dict(current_tags)
            for name, value in backup_tags.items():
                if name not in merged_tags:
                    merged_tags[name] = value

            # Merge tag_files: add missing by (tag_name, path)
            current_tf_keys = {(tf[0], tf[1]) for tf in current_tag_files if len(tf) >= 2}
            merged_tag_files = list(current_tag_files)
            for tf in backup_tag_files:
                if len(tf) >= 2 and (tf[0], tf[1]) not in current_tf_keys:
                    merged_tag_files.append(tf)

            # Merge tag_zims: add missing by (tag_name, zim_path, entry)
            current_tz_keys = {(tz[0], tz[1], tz[2]) for tz in current_tag_zims if len(tz) >= 3}
            merged_tag_zims = list(current_tag_zims)
            for tz in backup_tag_zims:
                if len(tz) >= 3 and (tz[0], tz[1], tz[2]) not in current_tz_keys:
                    merged_tag_zims.append(tz)

            merged_data = dict(
                tags=merged_tags,
                tag_files=merged_tag_files,
                tag_zims=merged_tag_zims,
                version=current_data.get('version', 0) + 1,
            )
            config_file.parent.mkdir(parents=True, exist_ok=True)
            self.write_config_data(merged_data, config_file)

        # Importing a backup is the user's choice: apply it whatever the versions.
        self.import_forced(send_events=send_events)


TAGS_CONFIG: TagsConfig = TagsConfig()
register_ownership(TagsConfig.file_name, Tag)
register_ownership(TagsConfig.file_name, TagFile)
TEST_TAGS_CONFIG: TagsConfig = None  # noqa


def get_tags_config() -> TagsConfig:
    global TEST_TAGS_CONFIG
    if isinstance(TEST_TAGS_CONFIG, ConfigFile):
        return TEST_TAGS_CONFIG

    global TAGS_CONFIG
    return TAGS_CONFIG


@contextlib.contextmanager
def test_tags_config():
    global TEST_TAGS_CONFIG
    TEST_TAGS_CONFIG = TagsConfig()
    yield
    TEST_TAGS_CONFIG = None


@register_switch_handler('save_tags_config')
def save_tags_config():
    """Schedule a background task to save all TagFiles to the config file.  If testing, save synchronously."""
    get_tags_config().dump_config()
    logger.info('save_tags_config complete')


def import_tags_config():
    """Reads the Tags and TagFiles from the config file, upserts them in the DB."""
    get_tags_config().import_config()
    sync_tags_directory.activate_switch()


save_tags_config: ActivateSwitchMethod


def _sync_tags_directory_tag_files(tags_directory: pathlib.Path, session: Session) -> List[pathlib.Path]:
    """Create all links that should be in the Tags Directory.  Return all links that should exist."""
    from wrolpi.files.models import FileGroup
    tag_files: List[Tuple[Tag, TagFile, FileGroup]] = session.query(Tag, TagFile, FileGroup) \
        .select_from(TagFile).join(TagFile.tag).join(TagFile.file_group).all()
    links = list()
    for tag, tag_file, file_group in tag_files:
        paths_map = file_group.get_tag_directory_paths_map()

        # Check if ANY source file still exists in this FileGroup.
        any_source_exists = any(file.is_file() for file in paths_map.keys())

        for file, link in paths_map.items():
            link = tags_directory / link

            if not file.is_file():
                if any_source_exists:
                    # Partial deletion - remove stale hardlink for this file.
                    if link.is_file():
                        logger.debug(f'Removing stale hardlink (source deleted): {link}')
                        link.unlink()
                    # Don't add to links - nothing should exist here.
                    continue
                else:
                    # ALL files deleted - preserve hardlinks as safety measure.
                    if link.is_file():
                        links.append(link)
                    continue

            need_create = False
            if not link.is_file():
                need_create = True
            else:
                # Check if existing link points to the correct file (same inode).
                # When a source file is replaced, the hardlink becomes stale.
                try:
                    if link.stat().st_ino != file.stat().st_ino:
                        # Hardlink is stale - points to old version of file.
                        link.unlink()
                        need_create = True
                except FileNotFoundError:
                    need_create = True

            if need_create:
                try:
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.hardlink_to(file)
                except FileNotFoundError:
                    logger.error(f'Failed to create link to file because it does not exist: {file}')
                    if PYTEST:
                        raise
            links.append(link)

    return links


# Files that should never be deleted from the Tags Directory.
IGNORED_TAG_DIRECTORY_FILES = {
    'README.txt',
}


def _delete_extra_tags_directory_paths(directory: pathlib.Path, links: List[pathlib.Path]):
    # Get all files that should exist.
    links = set(links)
    directory_paths = set(walk(directory))
    tags_directory_files = {i for i in directory_paths if i.is_file()}

    # Get all directories that should exist.
    link_directories = {i.parent for i in links if i.is_file()}
    tags_directory_directories = {i for i in directory_paths if i.is_dir()}

    # Delete any files that should not exist.
    ignored_files = {directory / i for i in IGNORED_TAG_DIRECTORY_FILES}
    extra_files = tags_directory_files - links - ignored_files
    for file in extra_files:
        if file.stat().st_nlink > 1:
            logger.debug(f'Deleting extra Tags Directory file: {file}')
            file.unlink()
        else:
            logger.warning(f'Refusing to delete Tag Directory file which does not have another link: {file}')

    # Delete any directories that should not exist.
    extra_directories = tags_directory_directories - link_directories
    for directory in extra_directories:
        if next(directory.iterdir(), None):
            logger.warning(f'Refusing to delete extra Tags Directory directory which contains files: {directory}')
        else:
            logger.debug(f'Deleting extra Tags Directory directory: {directory}')
            from wrolpi.files.lib import delete_directory
            delete_directory(directory)


def create_tags_directory(directory: pathlib.Path):
    directory.mkdir(parents=True, exist_ok=True)

    readme = directory / 'README.txt'
    readme.write_text('''This directory exists to allow a secondary way to access your tagged files.
Files are organized in a directory named after all the Tags they have been
tagged with.

WARNING: This directory is controlled by WROLPi, any files you put in here will
be AUTOMATICALLY DELETED!
''')


@register_switch_handler('sync_tags_directory')
def sync_tags_directory():
    """Synchronizes database Tags with the Tags directory (typically /media/wrolpi/tags).  Removes any
    files that do not belong in the Tags Directory."""
    wrolpi_config = get_wrolpi_config()
    if not wrolpi_config.tags_directory:
        logger.debug('Skipping tags directory sync because tags_directory setting is disabled')
        return

    with get_db_session() as session:
        try:
            tags_directory = get_tags_directory()
            create_tags_directory(tags_directory)

            links = _sync_tags_directory_tag_files(tags_directory, session)
            logger.debug(f'Tags Directory should contain {len(links)} links')
            _delete_extra_tags_directory_paths(tags_directory, links)
        except Exception as e:
            logger.error('Failed to sync DB with tags directory in media directory!', exc_info=e)
            raise


def get_tags(session: Session) -> List[dict]:
    with session_curs(session) as curs:
        curs.execute('''
                     SELECT t.id,
                            t.name,
                            t.color,
                            (SELECT COUNT(*) FROM tag_file WHERE tag_id = t.id)                        AS file_group_count,
                            (SELECT COUNT(*) FROM tag_zim WHERE tag_id = t.id)                         AS zim_entry_count,
                            (SELECT COUNT(*) FROM collection WHERE tag_id = t.id AND kind = 'channel') AS channel_count,
                            (SELECT COUNT(*) FROM collection WHERE tag_id = t.id AND kind = 'domain')  AS domain_count
                     FROM tag t
                     GROUP BY t.id, t.name, t.color
                     ORDER BY t.name
                     ''')
        tags = list(map(dict, curs.fetchall()))
    return tags


def get_recent_tags(session: Session, limit: int = 5) -> List[str]:
    with session_curs(session) as curs:
        curs.execute('''
                     SELECT t.name
                     FROM (SELECT tag_id, MAX(created_at) AS latest
                           FROM (SELECT tag_id, created_at
                                 FROM tag_file
                                 UNION ALL
                                 SELECT tag_id, created_at
                                 FROM tag_zim) AS combined
                           GROUP BY tag_id
                           ORDER BY latest DESC
                           LIMIT :limit) AS recent
                              JOIN tag t ON t.id = recent.tag_id
                     ORDER BY recent.latest DESC
                     ''', dict(limit=limit))
        return [row['name'] for row in curs.fetchall()]


def get_overlapping_tags(session: Session, tag_names: Union[str, List[str]], limit: int = 5) -> List[str]:
    if isinstance(tag_names, str):
        tag_names = [tag_names]

    limit_clause = 'LIMIT :limit' if limit is not None else ''

    params = dict(tag_count=len(tag_names), limit=limit)
    tag_names_placeholders = named_placeholders('tag_name', tag_names, params)

    with session_curs(session) as curs:
        curs.execute(f'''
                     WITH target_tags AS (SELECT id FROM tag WHERE name IN ({tag_names_placeholders})),
                     file_matching AS (
                         SELECT tf.file_group_id FROM tag_file tf
                         WHERE tf.tag_id IN (SELECT id FROM target_tags)
                         GROUP BY tf.file_group_id
                         HAVING COUNT(DISTINCT tf.tag_id) = :tag_count
                     ),
                     zim_matching AS (
                         SELECT tz.zim_id, tz.zim_entry FROM tag_zim tz
                         WHERE tz.tag_id IN (SELECT id FROM target_tags)
                         GROUP BY tz.zim_id, tz.zim_entry
                         HAVING COUNT(DISTINCT tz.tag_id) = :tag_count
                     ),
                     file_overlap AS (
                         SELECT tf.tag_id, COUNT(*) AS cnt FROM tag_file tf
                         WHERE tf.file_group_id IN (SELECT file_group_id FROM file_matching)
                         AND tf.tag_id NOT IN (SELECT id FROM target_tags) GROUP BY tf.tag_id
                     ),
                     zim_overlap AS (
                         SELECT tz.tag_id, COUNT(*) AS cnt FROM tag_zim tz
                         WHERE (tz.zim_id, tz.zim_entry) IN (SELECT zim_id, zim_entry FROM zim_matching)
                         AND tz.tag_id NOT IN (SELECT id FROM target_tags) GROUP BY tz.tag_id
                     ),
                     combined AS (
                         SELECT tag_id, SUM(cnt) AS total FROM (
                             SELECT tag_id, cnt FROM file_overlap UNION ALL SELECT tag_id, cnt FROM zim_overlap
                         ) AS all_overlap GROUP BY tag_id
                     )
                     SELECT t.name FROM combined c JOIN tag t ON t.id = c.tag_id ORDER BY c.total DESC {limit_clause}
                     ''', params)
        return [row['name'] for row in curs.fetchall()]


async def upsert_tag(session: Session, name: str, color: str, tag_id: int = None) -> Tag:
    old_name = None
    if tag_id:
        tag = Tag.find_by_id(session, tag_id)
        old_name = tag.name
        await tag.update_tag(session, name, color)
    else:
        tag = Tag()
        await tag.update_tag(session, name, color)
        session.add(tag)

    tag.flush()

    try:
        session.commit()
    except IntegrityError as e:
        # Conflicting name
        session.rollback()
        raise InvalidTag(f'Name already taken') from e

    save_tags_config.activate_switch()
    sync_tags_directory.activate_switch()
    if old_name and old_name != tag.name:
        # Downloads were renamed; save them only once they are committed.
        save_downloads_config.activate_switch()

    return tag


def tag_names_to_file_group_sub_select(tag_names: List[str], params: dict) -> Tuple[str, dict]:
    """Create the SQL necessary to filter FileGroup by the provided Tag names."""
    if not tag_names:
        return '', params

    # This select gets the FileGroup.id's which are tagged with the provided tag names.
    tag_names_placeholders = named_placeholders('tag_name', tag_names, params)
    sub_select = f'''
                 SELECT tf.file_group_id
                 FROM tag_file tf
                          JOIN tag t ON t.id = tf.tag_id AND t.name IN ({tag_names_placeholders})
                 GROUP BY tf.file_group_id
                 -- Match only FileGroups that have at least all the Tag names.
                 HAVING COUNT(DISTINCT t.name) = :tag_names_count \
                 '''
    params['tag_names_count'] = len(tag_names)
    return sub_select, params


def tag_append_sub_select_where(wheres: List[str], params: dict, tag_names: List[str], any_tag: bool = False) \
        -> Tuple[List[str], dict]:
    """Modify provided `wheres` and `params` to filter by `tag_names`, if any.  If no tag names are provided, but
    `any_tag` is True, then files will be filtered to only those that have at least one tag."""
    if any_tag and tag_names:
        raise RuntimeError('Cannot search for any tag, and list of tags.')

    if not tag_names and not any_tag:
        return wheres, params

    if any_tag:
        tags_sub_select = 'SELECT file_group_id FROM tag_file'
    else:
        tags_sub_select, params = tag_names_to_file_group_sub_select(tag_names, params)
    wheres.append(f'fg.id IN ({tags_sub_select})')
    return wheres, params


def tag_names_to_zim_sub_select(tag_names: List[str], zim_id: int = None) -> Tuple[str, dict]:
    if not tag_names:
        return '', dict()

    params = dict(tag_names_count=len(tag_names))
    tag_names_placeholders = named_placeholders('tag_name', tag_names, params)
    if zim_id:
        stmt = f'''
               SELECT tz.zim_id,
                      tz.zim_entry
               FROM tag_zim tz
                        JOIN tag t ON t.id = tz.tag_id AND t.name IN ({tag_names_placeholders})
               WHERE tz.zim_id = :zim_id
               GROUP BY tz.zim_id, tz.zim_entry
               -- Match only TagZimEntries that have all the Tag names.
               HAVING COUNT(DISTINCT t.name) = :tag_names_count \
               '''
        params['zim_id'] = zim_id
    else:
        stmt = f'''
               SELECT tz.zim_id,
                      tz.zim_entry
               FROM tag_zim tz
                        JOIN tag t ON t.id = tz.tag_id AND t.name IN ({tag_names_placeholders})
               GROUP BY tz.zim_id, tz.zim_entry
               -- Match only TagZimEntries that have all the Tag names.
               HAVING COUNT(DISTINCT t.name) = :tag_names_count \
               '''
    return stmt, params
