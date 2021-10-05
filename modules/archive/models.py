from sqlalchemy import Column, Integer, String, ForeignKey, types
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base, TZDateTime
from wrolpi.media_path import MediaPath


class DomainPath(types.TypeDecorator):
    impl = types.String

    def process_bind_param(self, value, dialect):
        return str(value) if value else None

    def process_result_value(self, value, dialect):
        if value:
            return MediaPath(value)


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    url_id = Column(Integer, ForeignKey('url.id', ondelete='cascade'))
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
