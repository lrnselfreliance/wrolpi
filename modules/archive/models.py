from typing import Generator

from sqlalchemy import Column, Integer, String, ForeignKey, Computed
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import ModelHelper, Base, tsvector
from wrolpi.dates import TZDateTime
from wrolpi.media_path import MediaPathType


class Archive(Base, ModelHelper):
    __tablename__ = 'archive'
    id = Column(Integer, primary_key=True)

    domain_id = Column(Integer, ForeignKey('domains.id'))
    domain = relationship('Domain', primaryjoin='Archive.domain_id==Domain.id')

    singlefile_path = Column(MediaPathType)
    readability_path = Column(MediaPathType)
    readability_json_path = Column(MediaPathType)
    readability_txt_path = Column(MediaPathType)
    screenshot_path = Column(MediaPathType)

    url = Column(String)
    title = Column(String)
    archive_datetime = Column(TZDateTime)
    contents = Column(String)

    textsearch = Column(tsvector, Computed('''setweight(to_tsvector('english'::regconfig, title), 'A') ||
            setweight(to_tsvector('english'::regconfig, contents), 'D')'''))

    def __repr__(self):
        return f'<Archive id={self.id} url={self.url} singlefile={self.singlefile_path}>'

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
            title=self.title,
            url=self.url,
        )
        return d

    def delete(self):
        self.unlink()

        session = Session.object_session(self)

        session.query(Archive).filter_by(id=self.id).delete()

        if self.domain:
            domain_archives = [i.id for i in self.domain.archives]
            if not domain_archives:
                self.domain.delete()


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
