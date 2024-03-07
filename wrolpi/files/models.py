import copy
import pathlib
import shutil
import urllib.parse
from datetime import datetime
from typing import List, Type, Optional

from sqlalchemy import Column, String, Computed, BigInteger, Boolean
from sqlalchemy import types
from sqlalchemy.orm import deferred, relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import Base, ModelHelper, tsvector, logger, recursive_map, get_media_directory, \
    get_relative_to_media_directory
from wrolpi.dates import TZDateTime, now, from_timestamp, strptime_ms, strftime
from wrolpi.db import optional_session
from wrolpi.errors import FileGroupIsTagged
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

    author = Column(String)  # name of the author, maybe even a URL
    data = Column(FancyJSON)  # populated by the modeler
    download_datetime = Column(TZDateTime)  # the date WROLPi downloaded this file.
    files = Column(FancyJSON, nullable=False)  # populated during discovery
    idempotency = Column(TZDateTime)  # used to track which files need to be deleted during refresh
    indexed = Column(Boolean, default=lambda: False, nullable=False)  # wrolpi.files.lib.apply_indexers
    length = Column(BigInteger)  # video duration, article words, etc.
    mimetype = Column(String)  # wrolpi.files.lib.get_mimetype
    model = Column(String)  # "video", "archive", "ebook", etc.
    modification_datetime = Column(TZDateTime)  # the modification date of the file on disk
    primary_path: pathlib.Path = Column(MediaPathType, nullable=False, unique=True)
    published_datetime = Column(TZDateTime)  # the date the creator published this file
    published_modified_datetime = Column(TZDateTime)  # the date the publisher modified this file
    size = Column(BigInteger, default=lambda: 0)
    title = Column(String)  # user-displayable title
    url = Column(String)  # the location where this file can be downloaded.
    viewed = Column(TZDateTime)  # the most recent time a User viewed this file.

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
            'author': self.author,
            'data': self.data,
            'directory': self.primary_path.parent,
            'download_datetime': self.download_datetime,
            'files': self.my_files(),
            'id': self.id,
            'key': self.primary_path,
            'length': self.length,
            'mimetype': self.mimetype,
            'model': self.model,
            'modified': self.modification_datetime or None,
            'name': self.primary_path.name,
            'primary_path': self.primary_path,
            'published_datetime': self.published_datetime,
            'published_modified_datetime': self.published_modified_datetime,
            'size': self.size,
            'suffix': suffix,
            'tags': tags,
            'title': self.title,
            'url': self.url,
            'viewed': self.viewed,
        }
        return d

    @property
    def name(self) -> str:
        if self.title:
            return self.title
        return self.primary_path.name

    def set_viewed(self):
        self.viewed = now()

    @optional_session
    def add_tag(self, tag: Tag, session: Session = None) -> TagFile:
        return tag.add_file_group_tag(self, session)

    @optional_session
    def remove_tag(self, tag: Tag, session: Session = None):
        tag.remove_file_group_tag(self, session)

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
        """Return all my Files that have text/vtt or text/srt mimetype."""
        return self.my_files('text/vtt', 'text/srt')

    def my_text_files(self) -> List[dict]:
        """Return all my Files that have a text mimetype.  But, do not include subtitle files."""
        text_files = self.my_files('text/')
        subtitle_paths = [i['path'] for i in self.my_subtitle_files()]
        return [i for i in text_files if i['path'] not in subtitle_paths]

    def my_ebook_files(self) -> List[dict]:
        return self.my_files('application/epub', 'application/x-mobipocket-ebook')

    def delete(self):
        """Delete this FileGroup record, and all of its files.

        @raise FileGroupIsTagged: If any tags are related to me."""
        if self.tag_files:
            raise FileGroupIsTagged(f'Cannot delete {self} because it has tags')

        for path in self.my_paths():
            path.unlink(missing_ok=True)

        if session := Session.object_session(self):
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
        """Create a new FileGroup which contains the provided file paths."""
        from wrolpi.files.lib import get_primary_file, get_mimetype

        existing_groups = session.query(FileGroup).filter(FileGroup.primary_path.in_(list(map(str, paths)))).all()
        if len(existing_groups) == 0:
            # These paths have not been used previously, create a new FileGroup.
            file_group = FileGroup()
            primary_path = get_primary_file(paths)
            file_group.primary_path = primary_path
            file_group.append_files(*paths)
            file_group.mimetype = get_mimetype(file_group.primary_path)
            session.add(file_group)
        elif len(existing_groups) == 1:
            # Found one FileGroup with these paths, no need to create a new FileGroup.
            file_group = existing_groups[0]
            primary_path = file_group.primary_path
        else:
            # Multiple FileGroups contain these paths as primary.
            primary_path = get_primary_file(paths)
            file_group: FileGroup = next(filter(lambda i: i.primary_path == primary_path, existing_groups), None)
            if not file_group:
                file_group = FileGroup.from_paths(session, primary_path)
            file_group.merge(existing_groups)

        if not isinstance(primary_path, pathlib.Path):
            raise ValueError('Cannot create FileGroup without a primary path.')

        file_group.modification_datetime = from_timestamp(max(i.stat().st_mtime for i in paths))
        file_group.size = sum(i.stat().st_size for i in paths)

        return file_group

    def find_by_id(id_: int, session: Session = None) -> 'FileGroup':
        fg = session.query(FileGroup).filter(FileGroup.id == id_).one_or_none()
        if not fg:
            raise RuntimeError(f'Unable to find FileGroup with id {id_}')
        return fg

    @staticmethod
    @optional_session
    def get_by_path(path, session) -> Optional['FileGroup']:
        file_group = session.query(FileGroup).filter(FileGroup.primary_path == str(path)).one_or_none()
        return file_group

    @property
    def tag_names(self) -> List[str]:
        return [i.tag.name for i in self.tag_files]

    def merge(self, file_groups: List['FileGroup']):
        """Consume the files and Tags of the provided FileGroups and attach them to this FileGroup.  Delete the provided
        FileGroups."""
        session = Session.object_session(self)

        collected_files = self.files.copy()
        for file_group in file_groups:
            if file_group.primary_path == self.primary_path:
                # Don't merge myself.
                continue

            for file in file_group.files:
                if file['path'] not in self.my_paths():
                    collected_files.append(file)
            # Move any applied Tags.
            for tag_file in file_group.tag_files:
                if tag_file.tag.name not in self.tag_names:
                    # Preserve the created at.
                    self.add_tag(tag_file.tag).created_at = tag_file.created_at
            session.delete(file_group)

        self.files = collected_files

    def move(self, new_primary_path: pathlib.Path, move_files: bool = True):
        """Move all files in this group to a new location."""
        from wrolpi.files.lib import split_path_stem_and_suffix
        if move_files and new_primary_path.exists():
            raise FileExistsError(f'Cannot move {self} to {new_primary_path} because it already exists.')

        new_name, _ = split_path_stem_and_suffix(new_primary_path, full=True)
        # Need a deepcopy because changes to self.files are ignored otherwise.
        new_files = copy.deepcopy(self.files)
        for idx, file in enumerate(new_files):
            _, suffix = split_path_stem_and_suffix(file['path'])
            new_path = pathlib.Path(f'{new_name}{suffix}')
            if move_files:
                shutil.move(file['path'], new_path)
            new_files[idx]['path'] = new_path
        self.files = new_files
        self.primary_path = new_primary_path
        # Need to re-index for self.data.
        self.indexed = False
        # Flush the changes to the FileGroup.
        Session.object_session(self).flush([self, ])

    @property
    def location(self):
        """Returns the URL that the FileGroup can be previewed."""
        parent = str(get_relative_to_media_directory(self.primary_path.parent))
        preview = str(get_relative_to_media_directory(self.primary_path))
        if parent == '.':
            # File is in the top of the media directory, App already shows top directory open.
            query = urllib.parse.urlencode(dict(preview=str(preview)))
        else:
            query = urllib.parse.urlencode(dict(folders=str(parent), preview=str(preview)))
        return f'/files?{query}'


class Directory(ModelHelper, Base):
    """A representation of a file directory in the media directory."""
    __tablename__ = 'directory'

    path: pathlib.Path = Column(MediaPathType, primary_key=True)
    name: str = Column(String, nullable=False)
    idempotency = Column(TZDateTime, default=lambda: now())

    def __json__(self):
        d = dict(
            path=self.path,
            name=self.name,
        )
        return d
