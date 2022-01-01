from typing import Generator

from sqlalchemy import Column, Integer, String, ForeignKey, Computed
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base, tsvector
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
    contents = Column(String)

    textsearch = Column(tsvector, Computed('''setweight(to_tsvector('english'::regconfig, title), 'A') ||
            setweight(to_tsvector('english'::regconfig, contents), 'D')'''))

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

    def __gt__(self, other) -> bool:
        """
        Compare Archives according to their archive datetime.
        """
        if not isinstance(other, Archive):
            raise ValueError(f'Cannot compare {type(other)} to Archive!')

        return self.archive_datetime > other.archive_datetime

    def __json__(self):
        url = None
        if self.url:
            url = dict(
                url=self.url.url,
                id=self.url.id,
            )
        d = dict(
            archive_datetime=self.archive_datetime,
            domain=self.domain.dict() if self.domain else None,
            domain_id=self.domain_id,
            id=self.id,
            readability_json_path=self.readability_json_path.path if self.readability_json_path else None,
            readability_path=self.readability_path.path if self.readability_path else None,
            readability_txt_path=self.readability_txt_path.path if self.readability_txt_path else None,
            screenshot_path=self.screenshot_path.path if self.screenshot_path else None,
            singlefile_path=self.singlefile_path.path if self.singlefile_path else None,
            status=self.status,
            title=self.title,
            url=url,
            url_id=self.url_id,
        )
        return d


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
        archives = filter(lambda i: i.singlefile_path and i.singlefile_path.path.exists(), self.archives)
        try:
            latest: Archive = max(archives)
            if latest:
                self.latest_id = latest.id
        except ValueError:
            # No archives exist!
            pass


class Domain(Base, ModelHelper):
    __tablename__ = 'domains'  # plural to avoid conflict
    id = Column(Integer, primary_key=True)

    domain = Column(String)
    directory = Column(MediaPathType)

    urls: InstrumentedList = relationship('URL', primaryjoin='Domain.id==URL.domain_id', order_by='URL.latest_datetime')

    def __repr__(self):
        return f'<Domain id={self.id} domain={self.domain} directory={self.directory}>'
