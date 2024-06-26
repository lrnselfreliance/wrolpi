from sqlalchemy import Column, Integer, Boolean, BigInteger

from modules.map import lib
from wrolpi import dates
from wrolpi.common import Base, ModelHelper
from wrolpi.media_path import MediaPathType


class MapFile(Base, ModelHelper):
    __tablename__ = 'map_file'
    id = Column(Integer, primary_key=True)

    path = Column(MediaPathType, unique=True, nullable=False)
    imported = Column(Boolean, default=False, nullable=False)
    size = Column(BigInteger)

    def __repr__(self):
        return f'<MapFile {self.path} imported={self.imported}>'

    def __json__(self) -> dict:
        return dict(
            id=self.id,
            imported=self.imported,
            path=self.path,
            seconds_to_import=(seconds := lib.seconds_to_import(self.size)),
            size=self.size,
            time_to_import=dates.seconds_to_timestamp(seconds),
        )
