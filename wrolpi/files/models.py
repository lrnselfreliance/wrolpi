import copy
import pathlib
import shutil
import urllib.parse
from datetime import datetime
from typing import List, Type, Optional, Iterable

from sqlalchemy import Column, String, Computed, BigInteger, Boolean, event, Index
from sqlalchemy import types
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import deferred, relationship, Session

from wrolpi.common import Base, ModelHelper, tsvector, logger, recursive_map, get_media_directory, \
    get_relative_to_media_directory, unique_by_predicate
from wrolpi.dates import TZDateTime, now, from_timestamp, strptime_ms, strftime
from wrolpi.db import get_db_session
from wrolpi.downloader import Download
from wrolpi.errors import FileGroupIsTagged, UnknownFile
from wrolpi.files import indexers
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile, save_tags_config, sync_tags_directory
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
    impl = JSONB

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
    __table_args__ = (
        Index('file_group_author_idx', 'author'),
        Index('file_group_directory_idx', 'directory'),
        Index('file_group_download_datetime_idx', 'download_datetime'),
        Index('file_group_effective_datetime_idx', 'effective_datetime'),
        Index('file_group_length_idx', 'length'),
        Index('file_group_mimetype_idx', 'mimetype'),
        Index('file_group_model_idx', 'model'),
        Index('file_group_modification_datetime_idx', 'modification_datetime'),
        Index('file_group_published_datetime_idx', 'published_datetime'),
        Index('file_group_published_modified_datetime_idx', 'published_modified_datetime'),
        Index('file_group_size_ix', 'size'),
        Index('file_group_textsearch_idx', 'textsearch'),
        Index('file_group_url_idx', 'url'),
        Index('file_group_viewed_idx', 'viewed'),
    )
    id: int = Column(BigInteger, primary_key=True)

    # Directory containing all files in this group (absolute path).
    # All paths in `files` and `data` are relative to this directory.
    directory: pathlib.Path = Column(MediaPathType, nullable=False)

    author = Column(String)  # name of the author, maybe even a URL
    censored = Column(Boolean)  # the file is no longer available for download
    data = Column(FancyJSON)  # populated by the modeler
    download_datetime = Column(TZDateTime)  # the date WROLPi downloaded this file.
    files = Column(FancyJSON)  # populated during discovery
    idempotency = Column(TZDateTime)  # used to track which files need to be deleted during refresh
    indexed = Column(Boolean, default=lambda: False)  # wrolpi.files.lib.apply_indexers
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

    # Columns updated by triggers.
    # `file_group_effective_datetime_trigger` and `update_effective_datetime` event handler
    effective_datetime = Column(TZDateTime)  # Equivalent to COALESCE(published_datetime, download_datetime)

    tag_files: Iterable[TagFile] = relationship('TagFile', cascade='all')

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

    def __json__(self) -> dict:
        from wrolpi.files.lib import split_path_stem_and_suffix
        _, suffix = split_path_stem_and_suffix(self.primary_path)

        # Get tag names with error handling
        tag_names = []
        for tag_file in self.tag_files:
            try:
                if tag_file.tag is not None:
                    tag_names.append(tag_file.tag.name)
            except AttributeError:
                if PYTEST:
                    raise
                # Log the error but continue processing other tags
                logger.error(
                    f"Found TagFile with problematic tag reference in __json__: {tag_file.id if hasattr(tag_file, 'id') else 'unknown'}")
        tags = sorted(tag_names)
        d = dict(
            author=self.author,
            censored=self.censored,
            data=self.data,
            directory=self.directory,
            download_datetime=self.download_datetime,
            files=self.my_files(),
            id=self.id,
            key=self.primary_path,
            length=self.length,
            mimetype=self.mimetype,
            model=self.model,
            modified=self.modification_datetime or None,
            name=self.primary_path.name,
            primary_path=self.primary_path,
            published_datetime=self.published_datetime,
            published_modified_datetime=self.published_modified_datetime,
            size=self.size,
            suffix=suffix,
            tags=tags,
            title=self.title,
            url=self.url,
            viewed=self.viewed,
        )
        return d

    @property
    def name(self) -> str:
        if self.title:
            return self.title
        return self.primary_path.name

    @property
    def full_primary_path(self) -> pathlib.Path:
        """Returns the complete absolute path to the primary file.

        Handles both old format (primary_path is absolute) and new format (directory + relative primary_path).
        """
        if self.directory:
            # New format: directory + relative filename
            return self.directory / self.primary_path
        # Old format: primary_path is already absolute
        return self.primary_path

    def resolve_path(self, relative_path: str | pathlib.Path) -> pathlib.Path:
        """Convert a relative filename to an absolute path using this FileGroup's directory.

        Handles both old format (path is already absolute) and new format (relative to directory).
        """
        if relative_path is None:
            return None
        path = pathlib.Path(relative_path) if isinstance(relative_path, str) else relative_path
        if path.is_absolute():
            # Old format: already absolute
            return path
        if self.directory:
            # New format: resolve relative to directory
            return self.directory / path
        # Fallback: use primary_path's parent as directory
        return self.primary_path.parent / path

    def set_viewed(self, viewed: datetime = None) -> datetime:
        """
        :param viewed: Used only for testing!
        :return: The datetime that was set.
        """
        self.viewed = viewed or now()
        return self.viewed

    def set_tags(self, session: Session, tag_names_or_ids: Iterable[str | int]):
        """Insert or Delete TagFiles as necessary to match the provided tags for this FileGroup."""
        tag_names_or_ids = list(tag_names_or_ids)
        if tag_names_or_ids and isinstance(tag_names_or_ids[0], str):
            tag_ids = {Tag.get_id_by_name(session, i) for i in tag_names_or_ids}
        else:
            tag_ids = set(tag_names_or_ids)

        existing_tag_ids = {i.tag_id for i in self.tag_files}
        if new_tag_ids := (tag_ids - existing_tag_ids):
            for tag_id in new_tag_ids:
                tag_file = TagFile(file_group_id=self.id, tag_id=tag_id)
                self.tag_files.append(tag_file)
            session.flush(self.tag_files)

        if deleted_tags := (existing_tag_ids - tag_ids):
            session.query(TagFile).filter(
                TagFile.file_group_id == self.id,
                TagFile.tag_id.in_(deleted_tags),
            ).delete(synchronize_session=False)
            # Refresh the relationship after deleting
            session.expire(self, ['tag_files'])

        # Save changes to config.
        save_tags_config.activate_switch()
        sync_tags_directory.activate_switch()

        return self.tag_files

    def add_tag(self, session: Session, tag_id: int | str) -> TagFile:
        """Add a tag to this FileGroup. `tag_id` can be an int (tag ID) or str (tag name)."""
        if isinstance(tag_id, str):
            tag_id = Tag.get_id_by_name(session, tag_id)
        tags = [i.tag_id for i in self.tag_files]
        tags.append(tag_id)
        tag_files = self.set_tags(session, tags)
        return next(i for i in tag_files if i.tag_id == tag_id)

    def untag(self, session: Session, tag_id: int | str):
        """Remove a tag from this FileGroup. `tag_id` can be an int (tag ID) or str (tag name)."""
        if isinstance(tag_id, str):
            tag_id = Tag.get_id_by_name(session, tag_id)
        tags = [i.tag_id for i in self.tag_files if i.tag_id != tag_id]
        self.set_tags(session, tags)

    def append_files(self, *paths: pathlib.Path):
        """Add all `paths` to this FileGroup.files.

        Paths are stored as filenames only (relative to directory).
        Also updates modification_datetime to include the new files.
        """
        from wrolpi.dates import from_timestamp
        from wrolpi.files.lib import get_mimetype
        new_files = list(self.files) if self.files else list()
        for path in paths:
            # Store just the filename, not the full path
            new_files.append(dict(path=path.name, mimetype=get_mimetype(path)))
        self.files = unique_by_predicate(new_files, lambda i: i['path'])
        # Update modification_datetime to include the new files' mtimes
        if paths:
            all_mtimes = [p.stat().st_mtime for p in paths if p.exists()]
            if self.modification_datetime:
                all_mtimes.append(self.modification_datetime.timestamp())
            if all_mtimes:
                self.modification_datetime = from_timestamp(max(all_mtimes))

    def my_files(self, *mimetypes: str) -> List[dict]:
        """Return all files related to this group that match any of the provided mimetypes.

        Paths are resolved to absolute paths using directory.
        Returns a new list (does not modify self.files in place).

        >>> FileGroup().my_files()
        >>> FileGroup().my_files('application/pdf')
        >>> FileGroup().my_files('video/')
        """
        if not self.files:
            logger.error(f'{self} has no files!')
            raise ValueError(f'{self} has no files!')

        # Create a new list with resolved paths (don't modify self.files in place)
        result = []
        for file_info in self.files:
            # Make a copy of each dict to avoid modifying the original
            file_copy = dict(file_info)
            path = pathlib.Path(file_info['path'])
            if not path.is_absolute() and self.directory:
                # New format: relative path, resolve using directory
                file_copy['path'] = self.directory / path
            else:
                # Old format or already absolute: keep as-is
                file_copy['path'] = path
            result.append(file_copy)

        if mimetypes:
            result = list(filter(lambda j: any(j['mimetype'].startswith(m) for m in mimetypes), result))

        if PYTEST:
            # Sort files to avoid random order during testing.
            return sorted(result, key=lambda j: j['path'])
        return result

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

    def my_epub_files(self) -> List[dict]:
        return self.my_files('application/epub')

    def my_mobi_files(self) -> List[dict]:
        return self.my_files('application/x-mobipocket-ebook')

    def my_html_files(self) -> List[dict]:
        html_files = self.my_files('text/html', 'application/octet-stream')
        html_files = [i for i in html_files if i['path'].name.endswith('.html')]
        return html_files

    def my_html_paths(self) -> List[pathlib.Path]:
        return [i['path'] for i in self.my_html_files()]

    def delete(self, add_to_skip_list: bool = True):
        """Delete this FileGroup record, and all of its files.

        @raise FileGroupIsTagged: If any tags are related to me."""
        if self.tag_files:
            raise FileGroupIsTagged(f'Cannot delete {self} because it has tags')

        for path in self.my_paths():
            path.unlink(missing_ok=True)

        if session := Session.object_session(self):
            from wrolpi.downloader import download_manager
            if self.url and (download := Download.get_by_url(session, self.url)):
                download.delete(add_to_skip_list)
            elif self.url and add_to_skip_list is True:
                download_manager.add_to_skip_list(self.url)
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
        from wrolpi.files.lib import get_primary_file, get_mimetype, sanitize_filename_surrogates

        # Sanitize any paths with invalid UTF-8 characters (renames files on disk if needed)
        paths = tuple(sanitize_filename_surrogates(p) for p in paths)

        existing_groups = session.query(FileGroup).filter(FileGroup.primary_path.in_(list(map(str, paths)))).all()
        logger.trace(f'FileGroup.from_paths: {len(existing_groups)=}')
        if len(existing_groups) == 0:
            # These paths have not been used previously, create a new FileGroup.
            file_group = FileGroup()
            primary_path = get_primary_file(paths)
            file_group.primary_path = primary_path
            file_group.append_files(*paths)
            session.add(file_group)
        elif len(existing_groups) == 1:
            # Found one FileGroup with these paths, no need to create a new FileGroup.
            file_group = existing_groups[0]
            file_group.append_files(*paths)
            primary_path = get_primary_file(file_group.my_paths())
        else:
            # Multiple FileGroups contain these paths as primary.
            primary_path = get_primary_file(paths)
            file_group: FileGroup = next(filter(lambda i: i.primary_path == primary_path, existing_groups), None)
            if not file_group:
                file_group = FileGroup.from_paths(session, primary_path)
            file_group.merge(existing_groups)

        if not isinstance(primary_path, pathlib.Path):
            raise ValueError('Cannot create FileGroup without a primary path.')

        file_group.directory = primary_path.parent
        file_group.primary_path = primary_path
        file_group.modification_datetime = from_timestamp(max(i.stat().st_mtime for i in paths))
        file_group.size = sum(i.stat().st_size for i in paths)
        file_group.mimetype = get_mimetype(file_group.primary_path)
        logger.trace(f'FileGroup.from_paths: {file_group}')

        return file_group

    @staticmethod
    def find_by_id(session: Session, id_: int) -> 'FileGroup':
        fg = session.query(FileGroup).filter(FileGroup.id == id_).one_or_none()
        if not fg:
            raise UnknownFile(f'Unable to find FileGroup with id {id_}')
        return fg

    @staticmethod
    def get_by_path(session: Session, path) -> Optional['FileGroup']:
        file_group = session.query(FileGroup).filter(FileGroup.primary_path == str(path)).one_or_none()
        return file_group

    @classmethod
    def get_by_any_file_path(cls, session: Session, path: pathlib.Path) -> Optional['FileGroup']:
        """Find a FileGroup that contains the given file path (primary or not).

        This method first checks if the path is a primary_path, and if not,
        searches for a FileGroup where the file is in the files list.
        """
        from sqlalchemy import text

        path = pathlib.Path(path)
        directory = str(path.parent)
        filename = path.name

        # First, try to find by primary_path (most common case)
        if file_group := cls.get_by_path(session, path):
            return file_group

        # Search for FileGroups in the same directory that contain this file
        file_groups = session.query(FileGroup).filter(FileGroup.directory == directory).all()
        for fg in file_groups:
            for file_info in fg.files:
                if file_info.get('path') == filename:
                    return fg

        return None

    @staticmethod
    def find_by_path(session: Session, path) -> 'FileGroup':
        file_group = FileGroup.get_by_path(session, path)
        if not file_group:
            raise UnknownFile(f'Unable to find FileGroup with path {path}')
        return file_group

    @classmethod
    def find_by_directory(cls, session: Session, directory: pathlib.Path, recursive: bool = False) -> List['FileGroup']:
        """Find all FileGroups in a directory (optionally recursive).

        Uses the indexed `directory` column for efficient lookups.
        """
        from sqlalchemy import or_
        directory_str = str(directory)
        if recursive:
            return session.query(cls).filter(
                or_(cls.directory == directory_str, cls.directory.like(f'{directory_str}/%'))
            ).all()
        return session.query(cls).filter(cls.directory == directory_str).all()

    @property
    def tag_names(self) -> List[str]:
        result = []
        for tag_file in self.tag_files:
            try:
                if tag_file.tag is not None:
                    result.append(tag_file.tag.name)
            except AttributeError:
                if PYTEST:
                    raise
                # Log the error but continue processing other tags
                logger.error(
                    f"Found TagFile with problematic tag reference: {tag_file.id if hasattr(tag_file, 'id') else 'unknown'}")
        return result

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
                if tag_file.tag is not None and tag_file.tag.name not in self.tag_names:
                    # Preserve the created at.
                    self.add_tag(session, tag_file.tag.id).created_at = tag_file.created_at
            session.delete(file_group)

        self.files = collected_files

    def move(self, new_primary_path: pathlib.Path):
        """Move all files in this group to a new location.

        With relative paths stored in `files` and `data`, we only need to:
        1. Move physical files to new location
        2. Update `directory` to point to new parent
        3. Update `primary_path` to the new path

        The relative filenames in `files` and `data` remain unchanged.
        """
        from wrolpi.files.lib import split_path_stem_and_suffix, glob_shared_stem, split_file_name_words

        if new_primary_path.exists():
            raise FileExistsError(f'Cannot move {self} to {new_primary_path} because it already exists.')

        # Adopt any new files when a FileGroup has multiple files.
        if len(self.my_files()) > 1:
            self.append_files(*glob_shared_stem(self.primary_path))

        new_name, _ = split_path_stem_and_suffix(new_primary_path, full=True)
        new_directory = new_primary_path.parent

        # Get current files with resolved absolute paths for moving
        current_files = self.my_files()

        # Ensure that all destination files do not yet exist before move.
        for file in current_files:
            _, suffix = split_path_stem_and_suffix(file['path'])
            new_path = pathlib.Path(f'{new_name}{suffix}')
            if new_path.exists():
                raise FileExistsError(f'Cannot move {self} to {new_path} because it already exists.')

        # Move physical files and collect new relative file entries
        new_files = []
        for file in current_files:
            old_path = file['path']  # Already resolved to absolute by my_files()
            _, suffix = split_path_stem_and_suffix(old_path)
            new_path = pathlib.Path(f'{new_name}{suffix}')
            if old_path.is_file():
                shutil.move(old_path, new_path)
                # Store just the filename (relative path)
                new_files.append({'path': new_path.name, 'mimetype': file['mimetype']})

        logger.debug(f'Moved FileGroup: {self.primary_path} -> {new_primary_path}')

        # Check if filename changed before updating primary_path
        old_name = self.primary_path.name
        filename_changed = old_name != new_primary_path.name

        # Update the FileGroup with new directory and relative files
        self.files = new_files
        self.directory = new_directory
        self.primary_path = new_primary_path

        # Update title and a_text only if filename changed
        if filename_changed:
            if self.title == old_name:
                self.title = new_primary_path.name
            self.a_text = split_file_name_words(new_primary_path.name)

        # Note: `data` now contains relative paths that don't need updating!
        # The filenames stay the same, only the directory changes.
        # Only re-index if there's no data yet (new file that hasn't been modeled).
        if not self.data:
            self.indexed = False

        # Note: Caller is responsible for flushing/committing

    @property
    def location(self):
        """Returns the URL that the FileGroup can be previewed."""
        klass = self.get_model_class()
        if klass:
            # Return the model location when possible.
            with get_db_session() as session:
                instance = klass.get_by_path(session, self.primary_path)
                if instance and hasattr(instance, 'location'):
                    return instance.location

        parent = str(get_relative_to_media_directory(self.directory))
        preview = str(get_relative_to_media_directory(self.primary_path))
        if parent == '.':
            # File is in the top of the media directory, App already shows top directory open.
            query = urllib.parse.urlencode(dict(preview=str(preview)))
        else:
            query = urllib.parse.urlencode(dict(folders=str(parent), preview=str(preview)))
        return f'/files?{query}'

    def get_model_class(self) -> Optional[Type[ModelHelper]]:
        """Return the class that is suitable for this FileGroup (usually based on mimetype), if any."""
        from modules.videos.models import Video
        from modules.archive.models import Archive
        from wrolpi.files.ebooks import EBook
        from modules.zim.models import Zim

        if Video.can_model(self):
            return Video
        elif EBook.can_model(self):
            return EBook
        elif Archive.can_model(self):
            return Archive
        elif Zim.can_model(self):
            return Zim

    def get_model_record(self) -> Optional[ModelHelper]:
        klass = self.get_model_class()
        if klass:
            with get_db_session() as session:
                return klass.get_by_path(session, self.primary_path)
        return None

    def do_model(self, session: Session) -> Optional[ModelHelper]:
        """Get/Create the Model record (Video/Archive/etc.) for this FileGroup, if any."""
        if model_class := self.get_model_class():
            # Always call do_model() to ensure FileGroup.data is updated when files change.
            # The model's do_model() should be idempotent (safe to call multiple times).
            model = model_class.do_model(session, self)
            logger.debug(f'modeled: {self} {model}')
            return model

        # Index the file if no models are available.
        logger.debug(f'no model class: {self}')
        self.do_index()
        self.indexed = True

    def get_tag_directory_paths_map(self) -> dict[pathlib.Path, str]:
        """Return all links that should exist for this FileGroup in the Tags Directory."""
        tag_names = self.tag_names
        if not tag_names:
            raise RuntimeError(f'Did not get any tag names for {self}')

        try:
            tag_names_str = ', '.join(sorted(tag_names))
            files = dict()
            for file in self.my_paths():
                files[file] = f'{tag_names_str}/{file.name}'
            return files
        except Exception as e:
            logger.error(f"Error in get_tag_directory_paths_map for {self}: {e}")
            raise


@event.listens_for(FileGroup, 'before_insert')
@event.listens_for(FileGroup, 'before_update')
def update_effective_datetime(mapper, connection, target):
    target.effective_datetime = target.published_datetime or target.download_datetime


class Directory(ModelHelper, Base):
    """A representation of a file directory in the media directory."""
    __tablename__ = 'directory'
    __table_args__ = (
        Index('directory_name_idx', 'name'),
    )

    path: pathlib.Path = Column(MediaPathType, primary_key=True)
    name: str = Column(String, nullable=False)
    idempotency = Column(TZDateTime, default=lambda: now())

    def __json__(self) -> dict:
        d = dict(
            path=self.path,
            name=self.name,
        )
        return d

    def __repr__(self):
        return f'<Directory path={repr(str(self.path))}>'
