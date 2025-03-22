import dataclasses
import functools
import pathlib
from collections import OrderedDict
from datetime import datetime
from typing import List, Tuple, OrderedDict as OrderedDictType, Dict, Optional, Set

from libzim import Archive, Searcher, Query, Entry, SuggestionSearcher
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, Text, tuple_, Boolean
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.exc import NoResultFound  # noqa

from modules.zim.errors import UnknownZimEntry, UnknownZimTagEntry, UnknownZim
from wrolpi import dates, tags
from wrolpi.common import Base, logger, get_relative_to_media_directory, ModelHelper
from wrolpi.dates import TZDateTime
from wrolpi.db import optional_session, get_db_curs
from wrolpi.downloader import Download, download_manager
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, tag_names_to_zim_sub_select

logger = logger.getChild(__name__)


@dataclasses.dataclass
class ZimMetadata:
    date: str
    creator: str
    description: str
    name: str
    publisher: str
    tags: str
    title: str

    def __json__(self) -> Dict:
        d = dict(
            date=self.date,
            creator=self.creator,
            description=self.description,
            name=self.name,
            publisher=self.publisher,
            tags=self.tags,
            title=self.title,
        )
        return d


class EntrySummary:
    zim_id: int
    path: str
    title: str

    def __json__(self) -> Dict:
        d = dict(
            zim_id=self.zim_id,
            path=self.path,
            title=self.title,
        )
        return d


class Zim(Base, ModelHelper):
    """Records of Zim files.

    Zim files stores wiki content (and much more) for offline usage. Zim files are compressed data that can be searched.
    """

    __tablename__ = 'zim'
    id = Column(Integer, primary_key=True)
    path: pathlib.Path = Column(MediaPathType, nullable=False)

    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), unique=True, nullable=False)
    file_group: FileGroup = relationship('FileGroup')
    auto_search = Column(Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<Zim id={self.id} file_group_id={self.file_group_id} path={self.path}>'

    def __json__(self) -> dict:
        d = dict(
            id=self.id,
            path=self.path,
            file_group_id=self.file_group_id,
            metadata=self.zim_metadata,
            size=self.file_group.size,
            auto_search=self.auto_search,
        )
        return d

    @staticmethod
    def from_paths(session: Session, *paths: pathlib.Path) -> 'Zim':
        file_group = FileGroup.from_paths(session, *paths)
        zim = Zim(path=file_group.primary_path, file_group=file_group)
        session.add(zim)
        session.flush([file_group, zim])
        return zim

    @staticmethod
    @optional_session
    def get_by_path(path: pathlib.Path, session: Session = None) -> Optional['Zim']:
        zim = session.query(Zim).filter_by(path=path).one_or_none()
        return zim

    @staticmethod
    @optional_session
    def find_by_path(path: pathlib.Path, session: Session = None) -> 'Zim':
        zim = Zim.get_by_path(path, session=session)
        if not zim:
            raise UnknownZim(f'Cannot find zim at path')
        return zim

    @staticmethod
    @optional_session
    def get_by_id(zim_id: int, session: Session = None) -> Optional['Zim']:
        zim = session.query(Zim).filter_by(id=zim_id).one_or_none()
        return zim

    @staticmethod
    @optional_session
    def find_by_id(zim_id: int, session: Session = None) -> 'Zim':
        zim = Zim.get_by_id(zim_id, session=session)
        if not zim:
            raise UnknownZim(f'Cannot find zim with ID {zim_id}')
        return zim

    def get_zim(self) -> Archive:
        if not self.path or not self.path.is_file():
            raise FileNotFoundError(f'{self} does not exist!')

        if not self.path.suffix != 'zim':
            raise FileNotFoundError(f'{self} is not a valid zim file!')

        zim = Archive(self.path)
        return zim

    def delete(self):
        session: Session = Session.object_session(self)
        self.path.unlink(missing_ok=True)
        session.delete(self)

    @staticmethod
    def can_model(file_group: FileGroup) -> bool:
        if file_group.primary_path.suffix.lower() == '.zim':
            return True
        return False

    @staticmethod
    def do_model(file_group: FileGroup, session: Session) -> 'Zim':
        from modules.zim.lib import model_zim
        zim = model_zim(file_group, session)
        return zim

    @functools.cached_property
    def zim_metadata(self) -> ZimMetadata:
        zim = self.get_zim()

        def _get_metadata(path: str):
            try:
                return zim.get_metadata(path).decode()
            except RuntimeError:
                return None

        metadata = ZimMetadata(
            date=_get_metadata('Date'),
            creator=_get_metadata('Creator'),
            description=_get_metadata('Description'),
            name=_get_metadata('Name'),
            publisher=_get_metadata('Publisher'),
            tags=_get_metadata('Tags'),
            title=_get_metadata('Title'),
        )
        return metadata

    def get_searcher(self) -> Searcher:
        searcher = Searcher(self.get_zim())
        return searcher

    def get_search(self, search_str: str):
        query = Query().set_query(search_str)
        searcher = self.get_searcher()
        search = searcher.search(query)
        return search

    def get_suggestion_searcher(self) -> SuggestionSearcher:
        searcher = SuggestionSearcher(self.get_zim())
        return searcher

    def estimate(self, search_str: str) -> int:
        """Count the number of Entry(s) that contain the `search_str`."""
        search = self.get_search(search_str)
        count = search.getEstimatedMatches()
        return count

    def search(self, search_str: str, offset: int = 0, limit: int = 10) -> List[str]:
        """Return the paths of the Entry(s) that contain the `search_str`."""
        search = self.get_search(search_str)
        results = list(search.getResults(offset, limit))
        return results

    def suggest(self, search_str: str, offset: int = 0, limit: int = 10) -> List[str]:
        """Return the paths of the Entry(s) that contain the `search_str`.  Also searches the titles."""
        searcher = self.get_suggestion_searcher()
        suggestions = searcher.suggest(search_str)
        results = list(suggestions.getResults(offset, limit))
        return results

    def get_entry(self, path: str) -> Optional[Entry]:
        """Search this Zim file for the provided Entry at the `path`."""
        zim = self.get_zim()
        try:
            entry = zim.get_entry_by_path(path)
        except KeyError:
            return None
        return entry

    def find_entry(self, path: str) -> Entry:
        """Search this Zim file for the provided Entry at the `path`.

        @raise UnknownZimEntry: if an entry at path does not exist."""
        if entry := self.get_entry(path):
            return entry

        raise UnknownZimEntry(f'Cannot find entry at {path=}')

    def tag_entry(self, tag_id_or_name: int | str, zim_entry: str) -> 'TagZimEntry':
        """Create a TagZimEntry for this Zim at the provided entry (path) for the provided Tag."""
        session = Session.object_session(self)

        # Ensure the entry exists.
        self.find_entry(zim_entry)

        tag = Tag.get_by_name(tag_id_or_name, session) if isinstance(tag_id_or_name, str) \
            else Tag.get_by_id(tag_id_or_name, session)
        tag_zim_entry = TagZimEntry(tag=tag, zim=self, zim_entry=zim_entry)
        session.add(tag_zim_entry)
        tags.save_tags_config.activate_switch()
        return tag_zim_entry

    def untag_entry(self, tag_id_or_name: int | str, zim_entry: str):
        """Removes any TagZimEntry of the Zim entry at the provided path for the provided Tag.

        @raise UnknownZimTagEntry: No entry exists to remove."""
        session = Session.object_session(self)
        tag = Tag.get_by_name(tag_id_or_name, session) if isinstance(tag_id_or_name, str) \
            else Tag.get_by_id(tag_id_or_name, session)
        tag_zim_entry = TagZimEntry.get_by_primary_keys(tag.id, self.id, zim_entry, session)
        if tag_zim_entry:
            session.delete(tag_zim_entry)
        else:
            raise UnknownZimTagEntry(f'Could not find at {repr(str(zim_entry))}')
        tags.save_tags_config.activate_switch()

    @staticmethod
    def _entries_with_tags_process(limit: int, offset: int, params: dict, session: Session, tags_sub_select: str):
        with get_db_curs() as curs:
            curs.execute(tags_sub_select, params)
            zim_ids_entries: List[Tuple[int, int]] = list(curs.fetchall())

        tag_zim_entries = session.query(TagZimEntry, Zim) \
            .join(Zim, Zim.id == TagZimEntry.zim_id) \
            .filter(tuple_(TagZimEntry.zim_id, TagZimEntry.zim_entry).in_(zim_ids_entries)) \
            .order_by(TagZimEntry.zim_id, TagZimEntry.zim_entry) \
            .offset(offset).limit(limit) \
            .distinct(TagZimEntry.zim_id, TagZimEntry.zim_entry)

        entries = list()
        for tag_zim_entry, zim in tag_zim_entries:
            entry = zim.find_entry(tag_zim_entry.zim_entry)
            entries.append(entry)

        return entries

    @optional_session
    def entries_with_tags(*args, session: Session = None, **kwargs) -> List[Entry]:
        """Return Zim Entries tagged with the provided names."""
        limit = int(kwargs.pop('limit', 10))
        offset = int(kwargs.pop('offset', 0))
        args = list(args)

        zim: Zim | None = args.pop(0) if isinstance(args[0], Zim) else None
        zim_id = zim.id if zim else None
        tag_names: List[str] = args.pop(0)

        if limit < 1:
            raise RuntimeError('Limit must be greater than zero')
        if args:
            raise RuntimeError('Extra unknown arguments')

        tags_sub_select, params = tag_names_to_zim_sub_select(tag_names, zim_id=zim_id)
        entries = Zim._entries_with_tags_process(limit, offset, params, session, tags_sub_select)
        return entries

    @functools.cached_property
    def all_entries(self) -> Set[EntrySummary]:
        """
        Iterates over all Entries in the Archive.  Ignores non-article entries (javascript, images, etc).
        """
        zim = self.get_zim()
        zim_id = self.id
        entry_count = zim.all_entry_count
        entries = set()
        for entry_id in range(entry_count):
            entry: Entry = zim._get_entry_by_id(entry_id)
            title = entry.title
            if title.startswith('m/') or title.startswith('-/') or title.startswith('I/'):
                continue

            summary = EntrySummary()
            summary.zim_id = zim_id
            summary.path = entry.path
            summary.title = title
            entries.add(summary)
        return entries


class Zims:
    """Convenience class which searches all known Zim files."""

    @staticmethod
    @optional_session
    def get_all(session: Session = None) -> List[Zim]:
        """Returns all Zim records."""
        zims = list()
        for zim in session.query(Zim).order_by(Zim.path):
            try:
                # It may not be possible to read the Zim file (drive not mounted), report and ignore.
                zim.get_zim()
                zims.append(zim)
            except Exception as e:
                logger.error(f'Failed to read Zim: {zim}', exc_info=e)
        return zims

    @classmethod
    @optional_session
    def estimate(cls, search_str: str, session: Session = None) -> OrderedDictType[Zim, int]:
        zims = cls.get_all(session=session)
        results = OrderedDict()
        for zim in zims:
            if zim.auto_search:
                results[zim] = zim.estimate(search_str)
        return results

    @classmethod
    @optional_session
    def entries_with_tags(cls, tag_names: List[str], session: Session = None) -> OrderedDictType[Zim, int]:
        zims = cls.get_all(session=session)
        results = OrderedDict()
        for zim in zims:
            results[zim] = len(zim.entries_with_tags(tag_names, session=session))
        return results


class TagZimEntry(Base):
    __tablename__ = 'tag_zim'

    tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
    tag: Tag = relationship('Tag')
    zim_id = Column(Integer, ForeignKey('zim.id', ondelete='CASCADE'), primary_key=True)
    zim: Zim = relationship('Zim')
    zim_entry: str = Column(Text, nullable=False, primary_key=True)
    created_at: datetime = Column(TZDateTime, default=dates.now)

    def __repr__(self):
        tag = self.tag_id
        if self.tag:
            tag = self.tag.name
        zim = self.zim_id
        if self.zim:
            zim = get_relative_to_media_directory(self.zim.path)
        return f'<TagZimEntry {tag=} zim={str(zim)} zim_entry={self.zim_entry}>'

    @staticmethod
    def get_by_primary_keys(tag_id: int, zim_id: int, zim_entry: str, session: Session):
        return session.query(TagZimEntry) \
            .filter_by(tag_id=tag_id, zim_id=zim_id, zim_entry=zim_entry) \
            .one_or_none()


class ZimSubscription(Base):
    __tablename__ = 'zim_subscription'

    id: int = Column(Integer, primary_key=True)
    name: str = Column(Text, unique=True, nullable=False)
    language: str = Column(Text, nullable=False)
    download_id: int = Column(Integer, ForeignKey('download.id', ondelete='CASCADE'), nullable=False)
    download: Download = relationship('Download', primaryjoin='ZimSubscription.download_id==Download.id')

    def __repr__(self):
        name = self.name
        language = self.language
        download_id = self.download_id
        return f'<ZimSubscription id={self.id} {name=} {language=} {download_id=}>'

    def __json__(self) -> dict:
        d = dict(
            id=self.id,
            name=self.name,
            language=self.language,
            download_id=self.download_id,
            download_url=self.download.url if self.download else None,
        )
        return d

    def change_download(self, url: str, frequency: int, session: Session):
        # A Zim file is found using the KiwixCatalogDownloader, then handled by the KiwixZimDownloader.
        old_url = self.download.url if self.download else url
        download = download_manager.get_or_create_download(old_url, session=session, reset_attempts=True)
        download.url = url
        download.frequency = frequency
        download.downloader = 'kiwix_catalog'
        download.sub_downloader = 'kiwix_zim'
        download.attempts = 0
        download.info_json = {'language': self.language, 'name': self.name}
        session.flush([download, ])
        self.download_id = download.id
        return download

    @staticmethod
    @optional_session
    def get_or_create(name: str, session: Session = None) -> 'ZimSubscription':
        subscription = session.query(ZimSubscription).filter_by(name=name).one_or_none()
        if subscription:
            return subscription

        subscription = ZimSubscription(name=name)
        return subscription
