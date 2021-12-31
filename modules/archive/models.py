from datetime import datetime
from typing import Generator

import pytz
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base
from wrolpi.dates import TZDateTime
from wrolpi.media_path import MediaPathType


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    url_id = Column(Integer, ForeignKey('url.id', ondelete='cascade'))
    url = relationship('URL', primaryjoin='Archive.url_id==URL.id')
    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')

    singlefile_path = Column(MediaPathType)
    readability_path = Column(MediaPathType)
    readability_json_path = Column(MediaPathType)
    readability_txt_path = Column(MediaPathType)
    screenshot_path = Column(MediaPathType)

    title = Column(String)
    archive_datetime = Column(TZDateTime)
    status = Column(String)

    def __repr__(self):
        return f'<Archive id={self.id} url_id={self.url_id} singlefile={self.singlefile_path}>'

    def my_paths(self) -> Generator:
        if self.singlefile_path:
            yield self.singlefile_path.path
        if self.readability_path:
            yield self.readability_path.path
        if self.readability_json_path:
            yield self.readability_json_path.path
        if self.readability_txt_path:
            yield self.readability_txt_path.path
        if self.screenshot_path:
            yield self.screenshot_path.path

    def unlink(self):
        """
        Remove any files in this archive.
        """
        # Don't fail if a file is missing, it could have been deleted manually.
        for path in self.my_paths():
            path.unlink(missing_ok=True)


class URL(Base, ModelHelper):
    __tablename__ = 'url'
    id = Column(Integer, primary_key=True)

    url = Column(String, unique=True)

    archives: InstrumentedList = relationship('Archive', primaryjoin='URL.id==Archive.url_id')
    latest_id = Column(Integer, ForeignKey('archive.id'))
    latest = relationship('Archive', primaryjoin='URL.latest_id==Archive.id')
    latest_datetime = Column(TZDateTime)
    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='URL.domain_id==Domain.id')

    def __repr__(self):
        return f'<URL id={self.id} url={self.url}>'

    def dict(self) -> dict:
        d = super().dict()
        d['latest'] = self.latest.dict() if self.latest else None
        d['domain'] = self.domain.dict()
        d['archives'] = [i.dict() for i in self.archives]
        return d

    def update_latest(self):
        """
        Set `latest` to the most recent Archive of this URL whose `singlefile` exists.
        """
        self.latest_id = None
        latest_datetime = datetime(2, 1, 1, 0, 0, 0).astimezone(tz=pytz.UTC)
        for archive in self.archives:
            if archive.singlefile_path and archive.singlefile_path.path.exists() and \
                    archive.archive_datetime >= latest_datetime:
                self.latest_id = archive.id


class Domain(Base, ModelHelper):
    __tablename__ = 'domains'  # plural to avoid conflict
    id = Column(Integer, primary_key=True)

    domain = Column(String)
    directory = Column(MediaPathType)

    urls: InstrumentedList = relationship('URL', primaryjoin='Domain.id==URL.domain_id', order_by='URL.latest_datetime')

    def __repr__(self):
        return f'<Domain id={self.id} domain={self.domain} directory={self.directory}>'
