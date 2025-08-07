import json
import pathlib
import re
from typing import Iterable, List, Optional

import pytz
from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, Session, validates
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi import dates
from wrolpi.common import ModelHelper, Base, logger, get_title_from_html, get_wrolpi_config, get_media_directory
from wrolpi.dates import now
from wrolpi.db import optional_session
from wrolpi.errors import UnknownArchive
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import TagFile
from wrolpi.vars import PYTEST
from .errors import InvalidArchive

logger = logger.getChild(__name__)

__all__ = ['Archive', 'Domain']

MATCH_URL = re.compile(r'^\s+?url:\s+?(http.*)', re.MULTILINE)
MATCH_DATE = re.compile(r'^\s+?saved date:\s+?(.*)', re.MULTILINE)


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), unique=True, nullable=False)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        if self.domain:
            return f'<Archive id={self.id} url={self.file_group.url} singlefile={repr(str(self.singlefile_path))} ' \
                   f'domain={self.domain.domain}>'
        return f'<Archive id={self.id} url={self.file_group.url} singlefile={repr(str(self.singlefile_path))}>'

    @staticmethod
    @optional_session
    def get_by_id(id_: int, session: Session = None) -> Optional['Archive']:
        """Attempt to find an Archive with the provided id.  Returns None if it cannot be found."""
        archive = session.query(Archive).filter_by(id=id_).one_or_none()
        return archive

    @staticmethod
    @optional_session
    def find_by_id(id_: int, session: Session = None) -> 'Archive':
        """Find an Archive with the provided id, raises an exception when no Archive is found.

        @raise UnknownArchive: if the Archive can not be found"""
        archive = Archive.get_by_id(id_, session=session)
        if not archive:
            raise UnknownArchive(f'Cannot find Archive with id {id_}')
        return archive

    @staticmethod
    @optional_session
    def get_by_path(path: pathlib.Path | str, session: Session = None) -> Optional['Archive']:
        archive = session.query(Archive).join(FileGroup).filter(FileGroup.primary_path == str(path)).one_or_none()
        return archive

    @staticmethod
    @optional_session
    def find_by_path(path: pathlib.Path | str, session: Session = None) -> Optional['Archive']:
        archive = Archive.get_by_path(path, session)
        if archive:
            return archive
        raise UnknownArchive(f'Cannot find Archive with path: {path}')

    @staticmethod
    def can_model(file_group: FileGroup) -> bool:
        from modules.archive.lib import is_singlefile_file
        if file_group.mimetype.startswith('text') and is_singlefile_file(file_group.primary_path):
            return True
        return False

    @staticmethod
    def do_model(file_group: FileGroup, session: Session) -> 'Archive':
        from modules.archive import model_archive
        archive = model_archive(file_group, session)
        archive.validate()
        file_group.indexed = True
        return archive

    def my_paths(self, *mimetypes: str) -> List[pathlib.Path]:
        return self.file_group.my_paths(*mimetypes)

    def my_files(self, *mimetypes: str) -> List[dict]:
        return self.file_group.my_files(*mimetypes)

    def unlink(self):
        """
        Remove any files in this archive.
        """
        # Don't fail if a file is missing, it could have been deleted manually.
        for path in self.my_paths():
            path.unlink(missing_ok=True)

    def __gt__(self, other) -> bool:
        """
        Compare Archives according to their archive datetime.
        """
        if not isinstance(other, Archive):
            raise ValueError(f'Cannot compare {type(other)} to Archive!')

        return self.file_group.published_datetime > other.file_group.published_datetime

    def delete(self):
        self.file_group.delete()

        session = Session.object_session(self)
        session.delete(self)

        if self.domain:
            # Delete a domain if it has no Archives.
            try:
                next(i.id for i in self.domain.archives)
            except StopIteration:
                self.domain.delete()

    @property
    def history(self) -> Iterable[Base]:
        """Get a list of Archives that share my URL."""
        session = Session.object_session(self)
        history = list(session.query(Archive).filter(
            Archive.id != self.id,
            FileGroup.url == self.file_group.url,
            FileGroup.url != None,  # noqa
        ) \
                       .join(FileGroup, FileGroup.id == Archive.file_group_id) \
                       .order_by(FileGroup.published_datetime))
        return history

    @property
    def singlefile_file(self) -> Optional[dict]:
        from modules.archive.lib import is_singlefile_file
        for file in self.file_group.my_html_files():
            if is_singlefile_file(file['path']):
                return file

    @property
    def singlefile_path(self) -> Optional[pathlib.Path]:
        if singlefile_file := self.singlefile_file:
            return singlefile_file['path']

    @property
    def readability_file(self) -> Optional[dict]:
        files = self.file_group.my_files('text/html')
        for file in files:
            if file['path'].name.endswith('.readability.html'):
                return file

    @property
    def readability_path(self) -> Optional[pathlib.Path]:
        if readability_file := self.readability_file:
            return readability_file['path']

    @property
    def readability_txt_file(self) -> Optional[dict]:
        files = self.file_group.my_files('text/plain', 'text/html')
        for file in files:
            if file['path'].name.endswith('.readability.txt'):
                return file

    @property
    def readability_txt_path(self) -> Optional[pathlib.Path]:
        if readability_txt_file := self.readability_txt_file:
            return readability_txt_file['path']

    @property
    def readability_json_file(self) -> Optional[dict]:
        files = self.file_group.my_files()
        for file in files:
            if file['path'].name.endswith('.readability.json'):
                return file

    @property
    def readability_json_path(self) -> Optional[pathlib.Path]:
        if readability_json_file := self.readability_json_file:
            return readability_json_file['path']

    @property
    def screenshot_file(self) -> Optional[dict]:
        files = self.file_group.my_files('image/')
        for file in files:
            return file

    @property
    def screenshot_path(self) -> Optional[pathlib.Path]:
        if screenshot_file := self.screenshot_file:
            return screenshot_file['path']

    def apply_readability_data(self):
        """Read the Readability JSON file, apply its contents to this record."""
        readability_json_path = self.readability_json_path
        if not readability_json_path:
            logger.debug(f'{self.singlefile_path} does not have an info json file')
            return
        if not readability_json_path.is_file():
            error = f'Cannot read data from {readability_json_path} because it not exist.'
            if PYTEST:
                raise ValueError(error)
            logger.error(error)
            return

        try:
            with readability_json_path.open() as fh:
                json_contents = json.load(fh)
                url = json_contents.get('url')
                title = json_contents.get('title')
        except Exception as e:
            raise InvalidArchive() from e

        # Readability is most trusted, it should overwrite any previous data.
        self.file_group.url = url or self.file_group.url
        self.file_group.title = title or self.file_group.title

    def apply_singlefile_data(self):
        """Read the start of the singlefile (if any) and extract any Archive information."""
        path = self.singlefile_path
        if not path:
            # Can't read contents of nothing.
            raise ValueError('Cannot read singlefile data when this has no files')

        if self.file_group.url and self.file_group.published_datetime:
            # This data has already been read.
            return

        with path.open('rt') as fh:
            head = fh.read(1000)
            if 'Page saved with SingleFile' not in head:
                logger.error(f'Could not find SingleFile header in {self}')
                return

            if not self.file_group.url:
                try:
                    if match := MATCH_URL.findall(head):
                        self.file_group.url = match[0].strip()
                except Exception as e:
                    logger.error(f'Could not get URL from singlefile {path}', exc_info=e)

            if not self.file_group.download_datetime:
                try:
                    if match := MATCH_DATE.findall(head):
                        dt = match[0].strip()
                        dt = ' '.join(dt.split(' ')[:5])
                        # SingleFile uses GMT.
                        dt = dates.strpdate(dt).replace(tzinfo=pytz.timezone('GMT'))
                        self.file_group.download_datetime = dt
                except Exception as e:
                    logger.error(f'Could not get archive date from singlefile {path}', exc_info=e)

    def apply_domain(self):
        """Get the domain from the URL."""
        from modules.archive.lib import get_or_create_domain
        domain = None
        if self.file_group.url:
            session = Session.object_session(self)
            if not session:
                raise ValueError('No session found!')
            domain = get_or_create_domain(session, self.file_group.url)
        # Clear domain if the URL is missing.
        self.domain_id = domain.id if domain else None

    def apply_singlefile_title(self):
        """Get the title from the Singlefile, if it's missing."""
        if self.singlefile_path and not self.file_group.title:
            self.file_group.title = get_title_from_html(self.singlefile_path.read_text())

    def apply_metadata(self):
        """Read and apply <meta> (and more) data from the Singlefile HTML."""
        from modules.archive import lib
        contents = self.singlefile_path.read_bytes()

        metadata = lib.parse_article_html_metadata(contents)
        if metadata.author:
            self.file_group.author = metadata.author
        if metadata.title:
            self.file_group.title = metadata.title
        if metadata.description:
            self.file_group.b_text = metadata.description
        if metadata.published_datetime:
            self.file_group.published_datetime = metadata.published_datetime
        if metadata.modified_datetime:
            self.file_group.published_modified_datetime = metadata.modified_datetime

    def validate(self):
        """Fill in any missing data about this Archive from its files."""
        try:
            self.apply_readability_data()
            self.apply_singlefile_data()
            self.apply_domain()
            self.apply_singlefile_title()
            self.apply_metadata()
        except Exception as e:
            logger.warning(f'Unable to validate {self}', exc_info=e)
            if PYTEST:
                raise

    @staticmethod
    def from_paths(session: Session, *paths: pathlib.Path) -> 'Archive':
        """Create a new Archive and FileGroup from the provided paths.

        The files will be read and Archive data extracted."""
        from modules.archive import model_archive
        file_group = FileGroup.from_paths(session, *paths)
        archive = model_archive(file_group, session)
        return archive

    def add_tag(self, tag_id_or_name: int | str, session: Session = None) -> TagFile:
        return self.file_group.add_tag(tag_id_or_name, session)

    @property
    def location(self):
        """The location where this Archive can be viewed in the UI."""
        return f'/archive/{self.id}'


class Domain(Base, ModelHelper):
    __tablename__ = 'domains'  # plural to avoid conflict
    id = Column(Integer, primary_key=True)

    domain = Column(String, nullable=False)
    directory = Column(MediaPathType)

    archives: InstrumentedList = relationship('Archive', primaryjoin='Archive.domain_id==Domain.id')

    def __repr__(self):
        return f'<Domain id={self.id} domain={self.domain} directory={self.directory}>'

    def delete(self):
        session = Session.object_session(self)
        session.execute('DELETE FROM archive WHERE domain_id=:id', dict(id=self.id))
        session.query(Domain).filter_by(id=self.id).delete()

    @validates('domain')
    def validate_domain(self, key, value: str):
        if not isinstance(value, str):
            raise ValueError('Domain must be a string')
        if len(value.split('.')) < 2:
            raise ValueError(f'Domain must contain at least one "." domain={repr(value)}')
        return value

    @property
    def download_directory(self) -> pathlib.Path:
        archive_destination = get_wrolpi_config().archive_destination

        now_ = now()
        variables = dict(
            domain=self.domain,
            year=now_.year,
            month=now_.month,
            day=now_.day,
        )
        archive_destination = archive_destination % variables
        archive_destination = pathlib.Path(archive_destination.lstrip('/'))
        if not archive_destination.is_absolute():
            archive_destination = get_media_directory() / archive_destination

        return archive_destination
