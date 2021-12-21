import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from sqlalchemy import Column, Integer, String, Boolean, JSON, Date, ARRAY, ForeignKey, Computed
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import Base, tsvector, ModelHelper, logger
from wrolpi.dates import now, TZDateTime
from wrolpi.db import get_db_curs
from wrolpi.downloader import Download
from wrolpi.errors import UnknownVideo, UnknownFile, UnknownDirectory
from wrolpi.media_path import MediaPathType, MediaPath

logger = logger.getChild(__name__)


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Video.channel_id==Channel.id', back_populates='videos')
    idempotency = Column(String)

    # File paths
    caption_path = Column(MediaPathType)
    description_path = Column(MediaPathType)
    ext = Column(String)
    info_json_path = Column(MediaPathType)
    poster_path = Column(MediaPathType)
    video_path = Column(MediaPathType)

    caption = Column(String)
    duration = Column(Integer)
    favorite = Column(TZDateTime)
    size = Column(Integer)
    source_id = Column(String)
    title = Column(String)
    upload_date = Column(TZDateTime)
    validated_poster = Column(Boolean, default=False)
    viewed = Column(TZDateTime)
    view_count = Column(Integer)
    url = Column(String)
    textsearch = Column(tsvector, Computed('''to_tsvector('english'::regconfig,
                                               ((COALESCE(title, ''::text) || ' '::text) ||
                                                COALESCE(caption, ''::text)))'''))

    def __repr__(self):
        return f'<Video id={self.id}, title={self.title}, path={self.video_path.path}, channel={self.channel_id} ' \
               f'source_id={self.source_id}>'

    def dict(self) -> dict:
        d = super().dict()
        if self.channel_id:
            d['channel'] = self.channel.dict()
        d['info_json'] = self.get_info_json()
        return d

    def get_minimize(self) -> dict:
        """
        Get a dictionary representation of this Video suitable for sending out the API.
        """
        from .common import minimize_video
        return minimize_video(self.dict())

    def _clear_paths(self):
        self.caption_path = None
        self.description_path = None
        self.ext = None
        self.info_json_path = None
        self.poster_path = None
        self.video_path = None

    def delete(self):
        """
        Remove all files related to this video.  Add it to it's Channel's skip list.

        Raises: UnknownFile if the video has no files.
        """
        from modules.videos.common import get_absolute_video_files
        video_files = get_absolute_video_files(self)
        for path in video_files:
            try:
                path.path.unlink()
            except FileNotFoundError:
                pass

        self._clear_paths()

        if not video_files:
            raise UnknownFile('No video files were deleted')

        self.add_to_skip_list()

    def add_to_skip_list(self):
        """
        Add this video to it's Channel's skip list.
        """
        if self.channel:
            self.channel.add_video_to_skip_list(self.source_id)

    def set_favorite(self, favorite: bool) -> Optional[datetime]:
        self.favorite = now() if favorite else None
        return self.favorite

    def set_viewed(self):
        self.viewed = now()

    def get_info_json(self) -> Optional[JSON]:
        """
        If this Video has an info_json file, return it's contents.  Otherwise, return None.
        """
        try:
            if self.info_json_path:
                with open(self.info_json_path.path, 'rb') as fh:
                    contents = json.load(fh)
                    return contents
        except UnknownFile:
            pass
        except UnknownDirectory:
            pass
        except Exception as e:
            logger.warning(f'Unable to parse info json {self.info_json_path}', exc_info=e)
            return None

    def get_video_description(self) -> Optional[str]:
        """
        Get the Video description from the file system.
        """
        # First try to get description from info_json file.
        info_json = self.get_info_json()
        if info_json:
            description = info_json.get('description')
            if description:
                return description

        if self.description_path:
            with open(self.description_path, 'rt') as fh:
                contents = fh.read()
                return contents

    def get_surrounding_videos(self):
        """
        Get the previous and next videos around this video.  The videos must be in the same channel.

        Example:
            >>> vid1 = Video(id=1, upload_date=10)
            >>> vid2 = Video(id=2, upload_date=20)
            >>> vid3 = Video(id=3, upload_date=30)
            >>> vid4 = Video(id=4)

            >>> vid1.get_surrounding_videos()
            (None, vid2)
            >>> vid2.get_surrounding_videos()
            (vid1, vid3)
            >>> vid3.get_surrounding_videos()
            (vid2, None)
            Video 4 has no upload date, so we can't place it in order.
            >>> vid4.get_surrounding_videos()
            (None, None)
        """
        session = Session.object_session(self)

        if not self.upload_date:
            # We can't place a video that has no upload date.
            return None, None

        with get_db_curs() as curs:
            query = '''
                    WITH numbered_videos AS (
                        SELECT id,
                            ROW_NUMBER() OVER (ORDER BY upload_date ASC) AS row_number
                        FROM video
                        WHERE
                            channel_id = %(channel_id)s
                            AND upload_date IS NOT NULL
                    )

                    SELECT id
                    FROM numbered_videos
                    WHERE row_number IN (
                        SELECT row_number+i
                        FROM numbered_videos
                        CROSS JOIN (SELECT -1 AS i UNION ALL SELECT 0 UNION ALL SELECT 1) n
                        WHERE
                        id = %(video_id)s
                    )
            '''
            curs.execute(query, dict(channel_id=self.channel_id, video_id=self.id))
            results = [i[0] for i in curs.fetchall()]

        # Assign the returned ID's to their respective positions relative to the ID that matches the video_id.
        previous_id = next_id = None
        for index, id_ in enumerate(results):
            if id_ == self.id:
                if index > 0:
                    previous_id = results[index - 1]
                if index + 1 < len(results):
                    next_id = results[index + 1]
                break

        # Fetch the videos by id, if they exist.
        previous_video = session.query(Video).filter_by(id=previous_id).one() if previous_id else None
        next_video = session.query(Video).filter_by(id=next_id).one() if next_id else None

        return previous_video, next_video

    def __json__(self):
        from modules.videos.common import minimize_video_info_json
        info_json = minimize_video_info_json(self.get_info_json()) if self.info_json_path else None

        d = dict(
            caption_path=self.caption_path,
            channel=self.channel,
            channel_id=self.channel_id,
            duration=self.duration,
            favorite=self.favorite,
            id=self.id,
            info_json=info_json,
            poster_path=self.poster_path,
            size=self.size,
            source_id=self.source_id,
            title=self.title,
            upload_date=self.upload_date,
            url=self.url,
            video_path=self.video_path,
            view_count=self.view_count,
            viewed=self.viewed,
        )
        return d


class Channel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    link = Column(String, nullable=False)
    idempotency = Column(String)
    url = Column(String)
    match_regex = Column(String)
    directory: MediaPath = Column(MediaPathType)
    skip_download_videos = Column(ARRAY(String))
    generate_posters = Column(Boolean)
    calculate_duration = Column(Boolean)
    download_frequency = Column(Integer)
    source_id = Column(String)

    info_json = Column(JSON)
    info_date = Column(Date)

    # Will be filled later by directory path relative to the media directory.
    _directory = None

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')

    def __repr__(self):
        return f'<Channel id={self.id}, name={repr(self.name)}>'

    def add_video_to_skip_list(self, source_id: str):
        if not source_id:
            raise UnknownVideo(f'Cannot skip video with empty source id: {source_id}')

        skip_download_videos = {i for i in self.skip_download_videos or [] if i}
        skip_download_videos.add(source_id)
        self.skip_download_videos = skip_download_videos

    def delete_with_videos(self):
        """
        Delete all Video records (but not video files) related to this Channel.  Then delete the Channel.
        """
        session = Session.object_session(self)
        # Delete the video records, but not the video files!
        session.query(Video).filter_by(channel_id=self.id).delete()
        if download := self.get_download():
            session.delete(download)

        session.delete(self)

    def update(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)

    def config_view(self) -> dict:
        """
        Retrieve the data about this Channel that should be stored in a config file.
        """
        config = dict(
            calculate_duration=self.calculate_duration,
            directory=str(self.directory.path),
            download_frequency=self.download_frequency,
            favorites={},
            generate_posters=self.generate_posters,
            match_regex=self.match_regex or '',
            name=self.name,
            skip_download_videos=self.skip_download_videos or [],
            source_id=self.source_id,
            url=self.url or '',
        )

        session = Session.object_session(self)
        favorites = session.query(Video).filter(Video.favorite != None, Video.channel_id == self.id).all()  # noqa
        favorites: List[Video]
        if favorites:
            config['favorites'] = {i.video_path.path.name: {'favorite': i.favorite} for i in favorites}

        return config

    def get_relative_path(self, path: Path, exists: bool = True):
        path = self.directory / path
        if exists and not path.exists():
            raise FileNotFoundError(f'{path} does not exist!')
        return path

    def get_download(self) -> Optional[Download]:
        """
        Get the Download row for this Channel.  If there isn't a Download, return None.
        """
        if not self.url:
            raise ValueError(f'Channel {self.name} does not have a URL to download!')

        session = Session.object_session(self)
        download = session.query(Download).filter_by(url=self.url).one_or_none()
        return download

    def __json__(self):
        d = dict(
            id=self.id,
            name=self.name,
            directory=self.directory,
            url=self.url,
            link=self.link,
        )
        return d
