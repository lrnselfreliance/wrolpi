import datetime
import json
import pathlib
import re
from typing import Generator

import pytz
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship, Session, validates
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base, logger
from wrolpi.dates import TZDateTime
from wrolpi.errors import InvalidArchive
from wrolpi.files.lib import split_path_stem_and_suffix
from wrolpi.files.models import File
from wrolpi.media_path import MediaPathType

logger = logger.getChild(__name__)


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')

    url = Column(String)
    title = Column(String)
    archive_datetime = Column(TZDateTime)
    validated = Column(Boolean)

    # Associated Files.
    singlefile_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    singlefile_file: File = relationship('File', primaryjoin='Archive.singlefile_path==File.path')
    readability_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    readability_file: File = relationship('File', primaryjoin='Archive.readability_path==File.path')
    readability_json_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    readability_json_file: File = relationship('File', primaryjoin='Archive.readability_json_path==File.path')
    readability_txt_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    readability_txt_file: File = relationship('File', primaryjoin='Archive.readability_txt_path==File.path')
    screenshot_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    screenshot_file: File = relationship('File', primaryjoin='Archive.screenshot_path==File.path')

    def __repr__(self):
        if self.domain:
            return f'<Archive id={self.id} url={self.url} singlefile={repr(str(self.singlefile_path))} ' \
                   f'domain={self.domain.domain}>'
        return f'<Archive id={self.id} url={self.url} singlefile={repr(str(self.singlefile_path))}>'

    def my_paths(self) -> Generator[pathlib.Path, None, None]:
        if self.singlefile_path:
            yield self.singlefile_path
        if self.readability_path:
            yield self.readability_path
        if self.readability_json_path:
            yield self.readability_json_path
        if self.readability_txt_path:
            yield self.readability_txt_path
        if self.screenshot_path:
            yield self.screenshot_path

    def my_files(self) -> Generator[File, None, None]:
        if self.singlefile_file:
            yield self.singlefile_file
        if self.readability_file:
            yield self.readability_file
        if self.readability_json_file:
            yield self.readability_json_file
        if self.readability_txt_file:
            yield self.readability_txt_file
        if self.screenshot_file:
            yield self.screenshot_file

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

    def __json__(self):
        stem, _ = split_path_stem_and_suffix(self.singlefile_path) if self.singlefile_path else (None, None)
        d = dict(
            archive_datetime=self.archive_datetime,
            domain=self.domain.dict() if self.domain else None,
            domain_id=self.domain_id,
            id=self.id,
            readability_json_path=self.readability_json_path,
            readability_path=self.readability_path,
            readability_txt_path=self.readability_txt_path,
            screenshot_path=self.screenshot_path,
            singlefile_path=self.singlefile_path,
            stem=stem,
            title=self.title,
            url=self.url,
        )
        return d

    def delete(self):
        self.unlink()

        session = Session.object_session(self)

        for file in self.my_files():
            session.delete(file)

        session.delete(self)

        if self.domain:
            domain_archives = [i.id for i in self.domain.archives]
            if not domain_archives:
                self.domain.delete()

    @property
    def alternatives(self):
        """
        Get a list of Archives that share my URL.
        """
        session = Session.object_session(self)
        alternatives = list(session.query(Archive).filter(
            Archive.id != self.id,
            Archive.url == self.url,
        ).order_by(Archive.archive_datetime))
        return alternatives

    @staticmethod
    def find_by_path(path, session: Session) -> Base:
        archive = session.query(Archive).filter_by(singlefile_path=path).one_or_none()
        return archive

    def read_singlefile_data(self):
        """
        Read the start of the singlefile (if any) and decode the Archive information.
        """
        match_url = re.compile(r'^\s+?url:\s+?(http.*)', re.MULTILINE)
        match_date = re.compile(r'^\s+?saved date:\s+?(.*)', re.MULTILINE)

        if self.singlefile_path:
            with self.singlefile_path.open('rt') as fh:
                head = fh.read(500)
                if 'Page saved with SingleFile' not in head:
                    return
                try:
                    if match := match_url.findall(head):
                        self.url = match[0].strip()
                except Exception as e:
                    logger.error(f'Could not get URL from singlefile {self.singlefile_path}', exc_info=e)
                try:
                    if match := match_date.findall(head):
                        dt = match[0].strip()
                        dt = ' '.join(dt.split(' ')[:5])
                        # SingleFile uses GMT.
                        dt = datetime.datetime.strptime(
                            dt,
                            '%a %b %d %Y %H:%M:%S'  # Fri Jun 17 2022 19:24:52
                        ).replace(tzinfo=pytz.timezone('GMT'))
                        self.archive_datetime = dt
                except Exception as e:
                    logger.error(f'Could not get archive date from singlefile {self.singlefile_path}', exc_info=e)

    def read_readability_data(self):
        """Read the Readability JSON file, apply its contents to this record."""
        from modules.archive.lib import get_or_create_domain, get_title_from_html

        readability_json_file = self.readability_json_file
        if not readability_json_file or not readability_json_file.path.is_file():
            logger.warning(f'Archive must have a readability json file: {self.singlefile_file.path}')
            return

        try:
            with readability_json_file.path.open() as fh:
                json_contents = json.load(fh)
                url = json_contents.get('url')
                title = json_contents.get('title')
        except Exception as e:
            raise InvalidArchive() from e

        domain = None
        if url:
            domain = get_or_create_domain(Session.object_session(self), url)

        if not title:
            title = get_title_from_html(self.singlefile_path.read_text())

        self.url = url
        self.title = title
        self.domain_id = domain.id if domain else None

    def validate(self):
        try:
            self.read_readability_data()
            self.read_singlefile_data()
            self.validated = True
        except Exception as e:
            logger.warning(f'Unable to validate {self}', exc_info=e)

    @staticmethod
    def find_by_paths(paths, session):
        archives = list(session.query(Archive).filter(Archive.singlefile_path.in_(paths)))
        return archives

    @property
    def primary_path(self):
        return self.singlefile_path


class Domain(Base, ModelHelper):
    __tablename__ = 'domains'  # plural to avoid conflict
    id = Column(Integer, primary_key=True)

    domain = Column(String)
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
