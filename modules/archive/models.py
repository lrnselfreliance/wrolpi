from pathlib import Path

from sqlalchemy import Column, Integer, String, ForeignKey, types
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base, TZDateTime


class DomainPath(types.TypeDecorator):
    impl = types.String

    def process_bind_param(self, value, dialect):
        return str(value) if value else None

    def process_result_value(self, value, dialect):
        if value:
            return Path(value)


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    url_id = Column(Integer, ForeignKey('url.id'))
    url = relationship('URL', primaryjoin='Archive.url_id==URL.id')
    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')

    singlefile_path = Column(DomainPath)
    readability_path = Column(DomainPath)
    readability_json_path = Column(DomainPath)
    readability_txt_path = Column(DomainPath)
    screenshot_path = Column(DomainPath)

    title = Column(String)
    archive_datetime = Column(TZDateTime)

    def __repr__(self):
        return f'<Archive id={self.id} url_id={self.url_id} singlefile={self.singlefile_path}>'

    def make_paths_relative(self):
        if not self.domain:
            raise Exception(f'No domain! {self}')

        d = self.domain.directory

        if str(self.singlefile_path).startswith('/'):
            self.singlefile_path = self.singlefile_path.relative_to(d)
        if str(self.readability_path).startswith('/'):
            self.readability_path = self.readability_path.relative_to(d)
        if str(self.readability_json_path).startswith('/'):
            self.readability_json_path = self.readability_json_path.relative_to(d)
        if str(self.readability_txt_path).startswith('/'):
            self.readability_txt_path = self.readability_txt_path.relative_to(d)
        if str(self.screenshot_path).startswith('/'):
            self.screenshot_path = self.screenshot_path.relative_to(d)


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

    def dict(self) -> dict:
        d = super().dict()
        d['latest'] = self.latest.dict()
        d['domain'] = self.domain.dict()
        d['archives'] = [i.dict() for i in self.archives]
        return d


class Domain(Base, ModelHelper):
    __tablename__ = 'domains'  # plural to avoid conflict
    id = Column(Integer, primary_key=True)

    domain = Column(String)
    directory = Column(String)

    urls: InstrumentedList = relationship('URL', primaryjoin='Domain.id==URL.domain_id', order_by='URL.latest_datetime')

    def __repr__(self):
        return f'<Domain id={self.id} domain={self.domain} directory={self.directory}>'
