from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Date, ARRAY

from api.db import Base


class Video(Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer)
    idempotency = Column(String)

    # File paths
    caption_path = Column(String)
    description_path = Column(String)
    ext = Column(String)
    info_json_path = Column(String)
    poster_path = Column(String)
    video_path = Column(String)

    caption = Column(String)
    duration = Column(Integer)
    favorite = Column(DateTime)
    size = Column(Integer)
    source_id = Column(String)
    title = Column(String)
    upload_date = Column(DateTime)
    validated_poster = Column(Boolean)
    viewed = Column(DateTime)

    def __repr__(self):
        return f'<Video(id={self.id}, title={self.title}, path={self.video_path})>'


class Channel(Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    link = Column(String)
    idempotency = Column(String)
    url = Column(String)
    match_regex = Column(String)
    directory = Column(String)
    skip_download_videos = Column(ARRAY(String))
    generate_posters = Column(Boolean)
    calculate_duration = Column(Boolean)
    download_frequency = Column(Integer)
    next_download = Column(Date)

    info_json = Column(JSON)
    info_date = Column(Date)

    def __repr__(self):
        return f'<Channel(id={self.id}, name={self.name})>'
