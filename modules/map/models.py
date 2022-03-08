from sqlalchemy import Column, Integer, Boolean, BigInteger

from wrolpi.common import Base, ModelHelper
from wrolpi.media_path import MediaPathType


class MapFile(Base, ModelHelper):
    __tablename__ = 'map_file'
    id = Column(Integer, primary_key=True)

    path = Column(MediaPathType, unique=True, nullable=False)
    imported = Column(Boolean, default=False, nullable=False)
    size = Column(BigInteger)

    def __json__(self):
        return {
            'id': self.id,
            'path': self.path,
            'imported': self.imported,
            'size': self.size,
        }
