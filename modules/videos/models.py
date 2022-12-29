import json
import pathlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator, Dict, List

from sqlalchemy import Column, Integer, String, Boolean, JSON, Date, ARRAY, ForeignKey
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import Base, ModelHelper, logger, get_media_directory, background_task
from wrolpi.dates import now, TZDateTime
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.downloader import Download, download_manager
from wrolpi.errors import UnknownVideo
from wrolpi.files.lib import refresh_directory_files_recursively, glob_shared_stem, split_path_stem_and_suffix
from wrolpi.files.models import File
from wrolpi.media_path import MediaPathType
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Video.channel_id==Channel.id', back_populates='videos')
    validated = Column(Boolean, default=False)

    censored = Column(Boolean, default=False)
    duration = Column(Integer)
    favorite = Column(TZDateTime)
    modification_datetime = Column(TZDateTime)
    size = Column(Integer)
    source_id = Column(String)
    title = Column(String)
    upload_date = Column(TZDateTime)
    url = Column(String)
    view_count = Column(Integer)
    viewed = Column(TZDateTime)

    # Associated Files
    caption_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    caption_file: File = relationship('File', primaryjoin='Video.caption_path==File.path')
    info_json_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    info_json_file: File = relationship('File', primaryjoin='Video.info_json_path==File.path')
    poster_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    poster_file: File = relationship('File', primaryjoin='Video.poster_path==File.path')
    video_path: pathlib.Path = Column(MediaPathType, ForeignKey('file.path', ondelete='CASCADE'))
    video_file: File = relationship('File', primaryjoin='Video.video_path==File.path')

    def __repr__(self):
        v = self.video_file
        if self.video_path:
            video_path = self.video_path.path if hasattr(self.video_path, 'path') else self.video_path
            v = video_path.relative_to(get_media_directory())
        return f'<Video id={self.id} title={repr(self.title)} path={v} channel={self.channel_id} ' \
               f'source_id={repr(self.source_id)}>'

    @classmethod
    def upsert(cls, video_file: File, session: Session):
        video = session.query(Video).filter_by(video_file=video_file).one_or_none()
        if not video:
            video = Video(video_file=video_file)
        video: Video
        video.video_path = video.video_path or video_file.path
        video.video_file = video.video_file or video_file
        video.size = video.video_path.stat().st_size
        session.add(video)

        video.find_my_files()

        # Claim the video file for this model.
        video.video_file.model = cls.__tablename__

        return video

    def my_paths(self) -> Generator[Path, None, None]:
        """Return all paths of this Video.  Returns nothing if all paths are None."""
        if self.poster_path:
            yield self.poster_path
        if self.caption_path:
            yield self.caption_path
        if self.info_json_path:
            yield self.info_json_path
        if self.video_path:
            yield self.video_path

    def my_files(self) -> Generator[File, None, None]:
        """Return all Files of this Video.  Returns nothing if all paths are None."""
        if self.poster_file:
            yield self.poster_file
        if self.caption_file:
            yield self.caption_file
        if self.info_json_file:
            yield self.info_json_file
        if self.video_file:
            yield self.video_file

    def delete(self):
        """
        Remove all files and File records related to this video.  Delete this Video record.
        Add it to it's Channel's skip list.
        """
        for path in self.my_paths():
            path.unlink(missing_ok=True)

        needs_save = bool(self.favorite)

        self.add_to_skip_list()
        self.favorite = None
        session = Session.object_session(self)
        session.commit()
        session.delete(self)

        for file in self.my_files():
            session.delete(file)

        if needs_save:
            # Save the Channels config.  This video was a favorite and that needs to be removed.
            from modules.videos.lib import save_channels_config
            save_channels_config(preserve_favorites=False)

    def add_to_skip_list(self):
        """Add this video to it's Channel's skip list."""
        if self.channel and self.source_id:
            self.channel.add_video_to_skip_list(self.source_id)

    def set_favorite(self, favorite: bool) -> Optional[datetime]:
        self.favorite = now() if favorite else None
        return self.favorite

    def set_viewed(self):
        self.viewed = now()

    def get_info_json(self) -> Optional[Dict]:
        """If this Video has an info_json file, return it's contents.  Otherwise, return None."""
        info_json_path = self.info_json_file.path if self.info_json_file else self.info_json_path
        if not info_json_path:
            return

        try:
            with info_json_path.open('rb') as fh:
                return json.load(fh)
        except FileNotFoundError:
            logger.warning(f'Unable to find info json file!  {info_json_path}')
            if self.video_path.is_file():
                # Clear out the info_json only if the video file exists.  We don't want to clear out the info_json if
                # the drive hasn't been mounted.
                self.info_json_file = self.info_json_path = None
            return None
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
        stem, _ = split_path_stem_and_suffix(self.video_path) if self.video_file else (None, None)

        d = dict(
            caption_path=self.caption_path,
            censored=self.censored,
            channel=self.channel,
            channel_id=self.channel_id,
            modification_datetime=self.modification_datetime,
            duration=self.duration,
            favorite=self.favorite,
            id=self.id,
            info_json=info_json,
            info_json_path=self.info_json_path,
            poster_path=self.poster_path,
            size=self.size,
            source_id=self.source_id,
            stem=stem,
            title=self.title,
            upload_date=self.upload_date,
            url=self.url,
            validated=self.validated,
            view_count=self.view_count,
            video_path=self.video_path.relative_to(get_media_directory()),
            viewed=self.viewed,
        )
        return d

    def validate(self, session: Session):
        """Perform a validation of this video and it's files.  Mark this video as validated if no errors occur."""
        if not self.video_file:
            # Can't validate if there is no video file.
            return False

        from .lib import validate_video
        try:
            validate_video(self, self.channel.generate_posters if self.channel else False, session)
            self.validated = True
        except Exception as e:
            logger.warning(f'Failed to validate video {self}', exc_info=e)

        return self.validated

    def find_my_files(self):
        """Search near the video file for it's associated files.  (poster, caption, etc.)"""
        from modules.videos.common import match_video_files
        if not self.video_path:
            raise ValueError("Can't find files when I don't have a video path!")

        # Associated files share the same stem, but different extensions.
        associated_paths = glob_shared_stem(self.video_path)
        associated_paths.pop(associated_paths.index(self.video_path))

        # Get the session from the video first, fallback to the video file.
        session: Session = Session.object_session(self) or Session.object_session(self.video_file)

        files = [File.upsert(i, session) for i in associated_paths]
        _, poster_file, description_file, caption_file, info_json_file = match_video_files(files)

        if poster_file:
            poster_file.do_index()
            poster_file.associated = True
        if caption_file:
            caption_file.do_index()
            caption_file.associated = True
        if info_json_file:
            info_json_file.do_index()
            info_json_file.associated = True

        session.flush([i for i in files])

        self.poster_file = poster_file
        self.caption_file = caption_file
        self.info_json_file = info_json_file

    @staticmethod
    def find_by_path(path, session):
        video = session.query(Video).filter_by(video_path=path).one_or_none()
        return video

    @staticmethod
    def find_by_paths(paths: List[pathlib.Path], session) -> List:
        videos = list(session.query(Video).filter(Video.video_path.in_(paths)))
        return videos

    @property
    def primary_path(self):
        return self.video_path


class Channel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String, unique=True)
    match_regex = Column(String)
    directory: pathlib.Path = Column(MediaPathType)
    skip_download_videos = Column(ARRAY(String))
    generate_posters = Column(Boolean, default=False)  # generating posters may delete files, and can be slow.
    calculate_duration = Column(Boolean, default=True)
    download_frequency = Column(Integer)
    source_id = Column(String)
    refreshed = Column(Boolean, default=False)

    info_json = Column(JSON)
    info_date = Column(Date)

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')

    def __repr__(self):
        return f'<Channel id={self.id}, name={repr(self.name)}>'

    def __eq__(self, other):
        if isinstance(other, Channel):
            return self.id == other.id
        return False

    def add_video_to_skip_list(self, source_id: str):
        if not source_id:
            raise UnknownVideo(f'Cannot skip video with empty source id: {source_id}')

        skip_download_videos = {i for i in self.skip_download_videos or [] if i}
        skip_download_videos.add(source_id)
        self.skip_download_videos = skip_download_videos

    def delete_with_videos(self):
        """Delete all Video records (but not video files) related to this Channel.  Then delete the Channel."""
        session = Session.object_session(self)
        # Delete the video records, but not the video files!
        session.query(Video).filter_by(channel_id=self.id).delete()
        if self.url and (download := self.get_download()):
            session.delete(download)

        session.delete(self)

    def update(self, data: dict):
        """
        Update the attributes of this Channel.  Will also update the Channel's Download, if it has one.
        """
        # Get the download before we change the URL.
        download = self.get_download()

        for key, value in data.items():
            setattr(self, key, value)

        # We need an absolute directory.
        if isinstance(self.directory, pathlib.Path) and not self.directory.is_absolute():
            self.directory = get_media_directory() / self.directory
        elif isinstance(self.directory, str) and not pathlib.Path(self.directory).is_absolute():
            self.directory = get_media_directory() / self.directory

        # All channels with a URL and download_frequency should have a download.
        session = Session.object_session(self)
        if download and not self.download_frequency:
            download_manager.delete_download(download.id, session)
        elif download and self.download_frequency:
            download.frequency = self.download_frequency
            download.url = self.url
            # Keep next_download if available.
            download.next_download = download.next_download or download_manager.calculate_next_download(download,
                                                                                                        session)
        elif not download and self.download_frequency and self.url:
            download = Download(frequency=self.download_frequency, url=self.url, downloader='video_channel')
            session.add(download)
            session.flush()
            download.next_download = download_manager.calculate_next_download(download, session)
        session.flush()

    def config_view(self) -> dict:
        """
        Retrieve the data about this Channel that should be stored in a config file.
        """
        config = dict(
            calculate_duration=self.calculate_duration,
            directory=str(self.directory),
            download_frequency=self.download_frequency,
            favorites={},
            generate_posters=self.generate_posters,
            match_regex=self.match_regex or '',
            name=self.name,
            skip_download_videos=self.skip_download_videos or [],
            source_id=self.source_id,
            url=self.url or None,
        )
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
            return None

        session = Session.object_session(self)
        download = session.query(Download).filter_by(url=self.url).one_or_none()
        return download

    def __json__(self):
        d = dict(
            id=self.id,
            name=self.name,
            directory=self.directory,
            url=self.url,
        )
        return d

    def dict(self, with_statistics: bool = False):
        d = super(Channel, self).dict()
        d['directory'] = self.directory.relative_to(get_media_directory()) if self.directory else None
        if with_statistics:
            d['statistics'] = self.get_statistics()
        return d

    def get_statistics(self):
        """
        Get statistics about this channel.
        """
        with get_db_curs() as curs:
            stmt = '''
                SELECT
                    SUM(size),
                    MAX(size),
                    COUNT(id)
                FROM video
                WHERE channel_id = %(id)s AND video_path IS NOT NULL
            '''
            curs.execute(stmt, dict(id=self.id))
            size, largest_video, video_count = curs.fetchone()
        statistics = dict(
            video_count=video_count,
            size=size,
            largest_video=largest_video,
        )
        return statistics

    async def refresh_files(self):
        """Refresh all files within this Channel's directory.  Mark this channel as refreshed."""
        logger.debug('Channel.refresh_files refresh_files')
        # Get this Channel's ID for later.  Refresh may take a long time.
        self_id = self.id

        # Refresh all files within this channel's directory first.
        await refresh_directory_files_recursively(self.directory)

        # Apply any info_json (discover censored videos, etc.) second.
        from modules.videos.common import apply_info_json
        if PYTEST:
            apply_info_json(self_id)
            self.refreshed = True
        else:

            # Perform info_json in background task.  Channel will be marked as refreshed after this completes.
            async def _():
                apply_info_json(self_id)
                with get_db_session(commit=True) as session:
                    channel: Channel = session.query(Channel).filter(Channel.id == self_id).one()
                    channel.refreshed = True

            background_task(_())
