import json
import pathlib
import re
from typing import Iterable, List, Optional, Union

import pytz
from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, Session, validates
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi import dates
from wrolpi.common import ModelHelper, Base, logger
from wrolpi.dates import TZDateTime
from wrolpi.db import optional_session
from wrolpi.errors import UnknownArchive
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile
from wrolpi.vars import PYTEST
from .errors import InvalidArchive

logger = logger.getChild(__name__)

__all__ = ['Archive', 'Domain']

MATCH_URL = re.compile(r'^\s+?url:\s+?(http.*)', re.MULTILINE)
MATCH_DATE = re.compile(r'^\s+?saved date:\s+?(.*)', re.MULTILINE)


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    archive_datetime = Column(TZDateTime)
    url = Column(String)

    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), unique=True, nullable=False)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        if self.domain:
            return f'<Archive id={self.id} url={self.url} singlefile={repr(str(self.singlefile_path))} ' \
                   f'domain={self.domain.domain}>'
        return f'<Archive id={self.id} url={self.url} singlefile={repr(str(self.singlefile_path))}>'

    @staticmethod
    @optional_session
    def get_by_id(id_: int, session: Session = None) -> Optional[Base]:
        """Attempt to find an Archive with the provided id.  Returns None if it cannot be found."""
        archive = session.query(Archive).filter_by(id=id_).one_or_none()
        return archive

    @staticmethod
    @optional_session
    def find_by_id(id_: int, session: Session = None) -> Base:
        """Find an Archive with the provided id, raises an exception when no Archive is found.

        @raise UnknownArchive: if the Archive can not be found"""
        archive = Archive.get_by_id(id_, session=session)
        if not archive:
            raise UnknownArchive(f'Cannot find Archive with id {id_}')
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

        return self.archive_datetime > other.archive_datetime

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
            Archive.url == self.url,
            Archive.url != None,  # noqa
        ).order_by(Archive.archive_datetime))
        return history

    @property
    def singlefile_file(self) -> Optional[dict]:
        from modules.archive.lib import is_singlefile_file
        files = self.file_group.my_files('text/html')
        for file in files:
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
        self.url = url or self.url
        self.file_group.title = title or self.file_group.title

    def apply_singlefile_data(self):
        """Read the start of the singlefile (if any) and extract any Archive information."""
        path = self.singlefile_path
        if not path:
            # Can't read contents of nothing.
            raise ValueError('Cannot read singlefile data when this has no files')

        if self.url and self.archive_datetime:
            # This data has already been read.
            return

        with path.open('rt') as fh:
            head = fh.read(1000)
            if 'Page saved with SingleFile' not in head:
                logger.error(f'Could not find SingleFile header in {self}')
                return

            if not self.url:
                try:
                    if match := MATCH_URL.findall(head):
                        self.url = match[0].strip()
                except Exception as e:
                    logger.error(f'Could not get URL from singlefile {path}', exc_info=e)

            if not self.archive_datetime:
                try:
                    if match := MATCH_DATE.findall(head):
                        dt = match[0].strip()
                        dt = ' '.join(dt.split(' ')[:5])
                        # SingleFile uses GMT.
                        dt = dates.strpdate(dt).replace(tzinfo=pytz.timezone('GMT'))
                        self.archive_datetime = dt
                except Exception as e:
                    logger.error(f'Could not get archive date from singlefile {path}', exc_info=e)

    def apply_domain(self):
        """Get the domain from the URL."""
        from modules.archive.lib import get_or_create_domain
        domain = None
        if self.url:
            session = Session.object_session(self)
            if not session:
                raise ValueError('No session found!')
            domain = get_or_create_domain(session, self.url)
        # Clear domain if the URL is missing.
        self.domain_id = domain.id if domain else None

    def apply_singlefile_title(self):
        """Get the title from the Singlefile, if it's missing."""
        from modules.archive.lib import get_title_from_html
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

    def add_tag(self, tag_or_tag_name: Union[Tag, str]) -> TagFile:
        tag = Tag.find_by_name(tag_or_tag_name) if isinstance(tag_or_tag_name, str) else tag_or_tag_name
        return self.file_group.add_tag(tag)


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
