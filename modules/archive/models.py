from pathlib import Path

from sqlalchemy import Column, Integer, String, ForeignKey, types, event
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
    status = Column(String)

    def __repr__(self):
        return f'<Archive id={self.id} url_id={self.url_id} singlefile={self.singlefile_path}>'

    def validate_paths(self):
        """
        Verify that all paths are relative to my Domain.
        """
        if not self.domain:
            return

        d = self.domain.directory
        paths = {'singlefile_path', 'readability_path', 'readability_json_path', 'readability_txt_path',
                 'screenshot_path'}
        for path in paths:
            value: Path = getattr(self, path)
            if isinstance(value, str):
                value = Path(value)

            if value and not value.is_relative_to(d):
                raise ValueError(f'Archive path {path} is not relative to domain {self.domain.directory}')


@event.listens_for(Archive, 'before_insert')
def archive_before_insert(mapper, connector, target: Archive):
    target.validate_paths()


@event.listens_for(Archive, 'before_update')
def archive_before_update(mapper, connector, target: Archive):
    target.validate_paths()


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
        d['latest'] = self.latest.dict() if self.latest else None
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
