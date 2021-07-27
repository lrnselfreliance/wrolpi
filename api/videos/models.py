from datetime import timedelta

from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Date, ARRAY, ForeignKey, Computed
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from api.common import Base, tsvector, ModelHelper, ChannelPath, PathColumn, today
from api.errors import UnknownVideo


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Video.channel_id==Channel.id')
    idempotency = Column(String)

    # File paths
    caption_path = Column(ChannelPath)
    description_path = Column(ChannelPath)
    ext = Column(String)
    info_json_path = Column(ChannelPath)
    poster_path = Column(ChannelPath)
    video_path = Column(ChannelPath)

    caption = Column(String)
    duration = Column(Integer)
    favorite = Column(DateTime)
    size = Column(Integer)
    source_id = Column(String)
    title = Column(String)
    upload_date = Column(DateTime)
    validated_poster = Column(Boolean, default=False)
    viewed = Column(DateTime)
    textsearch = Column(tsvector, Computed('''to_tsvector('english'::regconfig,
                                               ((COALESCE(title, ''::text) || ' '::text) ||
                                                COALESCE(caption, ''::text)))'''))

    def __repr__(self):
        return f'<Video(id={self.id}, title={self.title}, path={self.video_path}, channel={self.channel_id})>'

    def dict(self):
        d = super().dict()
        if self.channel_id:
            d['channel'] = self.channel.dict()
        return d


class Channel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    link = Column(String, nullable=False)
    idempotency = Column(String)
    url = Column(String)
    match_regex = Column(String)
    directory = Column(PathColumn)
    skip_download_videos = Column(ARRAY(String))
    generate_posters = Column(Boolean)
    calculate_duration = Column(Boolean)
    download_frequency = Column(Integer)
    next_download = Column(Date)

    info_json = Column(JSON)
    info_date = Column(Date)

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')

    def __repr__(self):
        return f'<Channel(id={self.id}, name={self.name})>'

    def add_video_to_skip_list(self, source_id):
        if source_id:
            skip_download_videos = {i for i in self.skip_download_videos or [] if i}
            skip_download_videos.add(source_id)
            self.skip_download_videos = skip_download_videos
        else:
            raise UnknownVideo(f'Cannot skip video with empty source id: {source_id}')

    def increment_next_download(self):
        """
        Set the next download predictably during the next download iteration.

        For example, two channels that download weekly will need to be downloaded on different days.  We want a channel
        to always be downloaded on it's day.  That may be Monday, or Tuesday, etc.

        This is true for all download frequencies (30 days, 90 days, etc.).

        The order that channels will be downloaded/distributed will be by `link`.
        """
        session = Session.object_session(self)

        # All the channels that share the my frequency.
        channel_group = session.query(self.__class__).filter_by(download_frequency=self.download_frequency)
        channel_group = list(channel_group.order_by(self.__class__.link).all())

        # My position in the channel group.
        index = channel_group.index(self)

        # The seconds between each download.
        chunk = self.download_frequency // len(channel_group)

        # My next download will be distributed by my frequency and my position.
        position = chunk * (index + 1)
        self.next_download = today() + timedelta(seconds=self.download_frequency + position)
