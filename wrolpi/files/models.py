import pathlib
from datetime import datetime
from typing import List, Type, Optional

from sqlalchemy import Column, String, Computed, BigInteger, Boolean
from sqlalchemy import types
from sqlalchemy.orm import deferred, relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import Base, ModelHelper, tsvector, logger, recursive_map, get_media_directory
from wrolpi.dates import TZDateTime, now, from_timestamp, strptime_ms, strftime
from wrolpi.db import optional_session
from wrolpi.files import indexers
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


def into_db(obj):
    if isinstance(obj, datetime):
        return strftime(obj)
    if isinstance(obj, pathlib.Path):
        return str(obj)
    return obj


def out_of_db(media_directory, obj):
    if obj and isinstance(obj, str) and obj.startswith(media_directory):
        return pathlib.Path(obj)
    if obj and isinstance(obj, str) and obj[0].isdigit():
        try:
            return strptime_ms(obj)
        except Exception:
            # Wasn't a datetime after all.
            pass
    return obj


class FancyJSON(types.TypeDecorator):
    """Converts pathlib.Path to strings when moving into DB, and vice versa.

    Converts datetime to ISO strings when moving into DB, and vice versa.
    """
    impl = types.JSON

    def process_bind_param(self, value, dialect):
        if value:
            # datetime(2020, 1, 1, 0, 0, 0) <-> '2020-01-01T00:00:00'
            value = recursive_map(value, into_db)
        return value

    def process_result_value(self, value, dialect) -> None:
        if value:
            media_directory = str(get_media_directory())
            value = recursive_map(value, lambda i: out_of_db(media_directory, i))
        return value


class FileGroup(ModelHelper, Base):
    __tablename__ = 'file_group'
    id: int = Column(BigInteger, primary_key=True)

    data = Column(FancyJSON)  # populated by the modeler
    files = Column(FancyJSON, nullable=False)  # populated during discovery
    full_stem = Column(String, unique=True)
    idempotency = Column(TZDateTime)
    indexed = Column(Boolean, default=lambda: False, nullable=False)
    mimetype = Column(String)  # wrolpi.files.lib.get_mimetype
    model = Column(String)  # "video", "archive", "ebook", etc.
    modification_datetime = Column(TZDateTime)
    # the Path of the file that can be modeled or indexed.
    primary_path = Column(MediaPathType, nullable=False, unique=True)
    size = Column(BigInteger, default=lambda: 0)
    title = Column(String)

    tag_files: InstrumentedList = relationship('TagFile', cascade='all')

    a_text = deferred(Column(String))
    b_text = deferred(Column(String))
    c_text = deferred(Column(String))
    d_text = deferred(Column(String))
    textsearch = deferred(
        Column(tsvector, Computed('''
            setweight(to_tsvector('english'::regconfig, COALESCE(a_text, '')), 'A'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(b_text, '')), 'B'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(c_text, '')), 'C'::"char") ||
            setweight(to_tsvector('english'::regconfig, COALESCE(d_text, '')), 'D'::"char")
            ''')))

    def __repr__(self):
        m = f'model={self.model}' if self.model else f'mimetype={self.mimetype}'
        return f'<FileGroup id={self.id} {m} primary_path={repr(str(self.primary_path))}>'

    def __json__(self):
        from wrolpi.files.lib import split_path_stem_and_suffix
        _, suffix = split_path_stem_and_suffix(self.primary_path)
        tags = sorted([i.tag.name for i in self.tag_files])
        d = {
            'data': self.data,
            'directory': self.primary_path.parent,
            'files': self.my_files(),
            'full_stem': pathlib.Path(self.full_stem) if self.full_stem else None,
            'id': self.id,
            'mimetype': self.mimetype,
            'model': self.model,
            'modified': self.modification_datetime or None,
            'name': self.primary_path.name,
            'primary_path': self.primary_path,
            'size': self.size,
            'suffix': suffix,
            'tags': tags,
            'title': self.title,
            'key': self.primary_path,
        }
        return d

    @property
    def name(self) -> str:
        if self.title:
            return self.title
        return self.primary_path.name

    @optional_session
    def add_tag(self, tag: Tag, session: Session = None) -> TagFile:
        return tag.add_tag(self, session)

    @optional_session
    def remove_tag(self, tag: Tag, session: Session = None):
        tag.remove_tag(self, session)

    def append_files(self, *paths: pathlib.Path):
        """Add all `paths` to this FileGroup.files."""
        from wrolpi.files.lib import get_mimetype
        new_files = list(self.files) if self.files else list()
        for file in paths:
            new_files.append(dict(path=file, mimetype=get_mimetype(file)))
        self.files = new_files

    def my_files(self, *mimetypes: str) -> List[dict]:
        """Return all files related to this group that match any of the provided mimetypes.

        >>> FileGroup().my_files()
        >>> FileGroup().my_files('application/pdf')
        >>> FileGroup().my_files('video/')
        """
        files = self.files
        if not files:
            logger.error(f'{self} has no files!')
            raise ValueError(f'{self} has no files!')

        # Convert path strings to Paths.
        for i in range(len(files)):
            files[i]['path'] = pathlib.Path(files[i]['path'])

        if mimetypes:
            files = list(filter(lambda i: any(i['mimetype'].startswith(m) for m in mimetypes), files))

        # Sort files to avoid random order.
        return sorted(files, key=lambda i: i['path'])

    def my_paths(self, *mimetypes: str) -> List[pathlib.Path]:
        return [i['path'] for i in self.my_files(*mimetypes)]

    def my_video_files(self):
        """Return all my Files that are videos."""
        return self.my_files('video/')

    def my_json_files(self):
        """Return all my Files that are JSON."""
        return self.my_files('application/json')

    def my_poster_files(self) -> List[dict]:
        """Return all my Files that are images."""
        return self.my_files('image/')

    def my_subtitle_files(self) -> List[dict]:
        """Return all my Files that have text/srt or text/vtt mimetype."""
        return self.my_files('text/srt', 'text/vtt')

    def my_text_files(self) -> List[dict]:
        """Return all my Files that have a text mimetype.  But, do not include subtitle files."""
        text_files = self.my_files('text/')
        subtitle_paths = [i['path'] for i in self.my_subtitle_files()]
        return [i for i in text_files if i['path'] not in subtitle_paths]

    def my_ebook_files(self) -> List[dict]:
        return self.my_files('application/epub', 'application/x-mobipocket-ebook')

    def delete(self):
        """Delete this FileGroup record, and all of its files."""
        for path in self.my_paths():
            path.unlink()

        session = Session.object_session(self)
        if session:
            session.delete(self)

    @property
    def indexer(self) -> Type[indexers.Indexer]:
        if not self.mimetype:
            raise ValueError(f'Cannot find indexer because {self} does not have a mimetype!')
        return indexers.find_indexer(self.mimetype)

    def do_index(self):
        """Gather any missing information about this file group.  Index the contents of this file using an Indexer."""
        try:
            # Get the indexer on a separate line for debugging.
            indexer = self.indexer
            # Only read the contents of the file once.
            start = now()
            self.a_text, self.b_text, self.c_text, self.d_text = indexer.create_index(self.primary_path)
            self.title = self.title or self.primary_path.name
            if (total_seconds := (now() - start).total_seconds()) > 1:
                logger.info(f'Indexing {self.primary_path} took {total_seconds} seconds')
        except Exception as e:
            logger.error(f'Failed to index {self}', exc_info=e)
            if PYTEST:
                raise

    @classmethod
    def from_paths(cls, session: Session, *paths: pathlib.Path) -> 'FileGroup':
        from wrolpi.files.lib import get_primary_file, split_path_stem_and_suffix, get_mimetype
        file_group = FileGroup()

        file_group.append_files(*paths)
        file_group.full_stem, _ = split_path_stem_and_suffix(paths[0], full=True)
        file_group.primary_path = get_primary_file(paths)
        file_group.mimetype = get_mimetype(file_group.primary_path)
        file_group.modification_datetime = from_timestamp(max(i.stat().st_mtime for i in paths))
        file_group.size = sum(i.stat().st_size for i in paths)

        session.add(file_group)
        return file_group

    @staticmethod
    @optional_session
    def find_by_path(path, session) -> Optional['FileGroup']:
        file_group = session.query(FileGroup).filter(FileGroup.primary_path == str(path)).one_or_none()
        return file_group
