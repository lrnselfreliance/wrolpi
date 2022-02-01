from sqlalchemy import Integer, Column, String, Computed
from sqlalchemy.orm import deferred

from wrolpi.common import Base, ModelHelper, get_media_directory, tsvector
from wrolpi.dates import TZDateTime
from wrolpi.media_path import MediaPathType


class File(ModelHelper, Base):
    __tablename__ = 'file'
    id = Column(Integer, primary_key=True)

    mimetype = Column(String)
    modification_datetime = Column(TZDateTime)
    path = Column(MediaPathType)
    size = Column(Integer)
    title = Column(String)

    textsearch = deferred(
        Column(tsvector, Computed('''to_tsvector('english'::regconfig, (COALESCE(title, ''::text) || ' '::text))''')))

    def __repr__(self):
        return f'<File id={self.id} path={self.path.relative_to(get_media_directory())} mime={self.mimetype}>'

    def __json__(self):
        d = dict(
            id=self.id,
            mimetype=self.mimetype,
            modification_datetime=self.modification_datetime,
            path=self.path.path.relative_to(get_media_directory()),
            size=self.size,
            title=self.title,
        )
        return d
