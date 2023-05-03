import datetime
import json
import pathlib
from pathlib import Path
from typing import Optional, Dict, List, Union

from sqlalchemy import Column, Integer, String, Boolean, JSON, Date, ARRAY, ForeignKey, BigInteger, any_
from sqlalchemy.orm import relationship, Session, deferred
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.captions import read_captions
from wrolpi.common import Base, ModelHelper, logger, get_media_directory, background_task
from wrolpi.dates import now, TZDateTime
from wrolpi.db import get_db_curs, get_db_session, optional_session
from wrolpi.downloader import Download, download_manager
from wrolpi.errors import UnknownVideo
from wrolpi.files.lib import refresh_files, split_path_stem_and_suffix
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)

    duration = Column(Integer)
    source_id = Column(String)
    upload_date: datetime.datetime = Column(TZDateTime)
    url = Column(String)
    view_count = Column(Integer)
    viewed = Column(TZDateTime)

    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Video.channel_id==Channel.id', back_populates='videos')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), unique=True, nullable=False)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        v = None
        if self.video_path:
            v = self.video_path.relative_to(get_media_directory())
        return f'<Video id={self.id} title={repr(self.file_group.title)} path={v} channel={self.channel_id} ' \
               f'source_id={repr(self.source_id)}>'

    def __json__(self) -> dict:
        d = self.file_group.__json__()

        channel = None
        if self.channel:
            channel = dict(id=self.channel.id, name=self.channel.name)

        # Put live data in "video" instead of "data" to avoid confusion on the frontend.
        d['video'] = dict(
            caption=self.file_group.d_text,
            caption_files=self.caption_files,
            channel=channel,
            channel_id=self.channel_id,
            description=self.file_group.c_text or self.get_video_description(),
            duration=self.duration,
            id=self.id,
            info_json_file=self.info_json_file,
            info_json_path=self.info_json_path,
            poster_file=self.poster_file,
            poster_path=self.poster_path,
            source_id=self.source_id,
            stem=split_path_stem_and_suffix(self.video_path)[0],
            upload_date=self.upload_date.isoformat() if self.upload_date else None,
            url=self.url,
            video_path=self.video_path,
            view_count=self.view_count,
        )
        return d

    def delete(self):
        """Remove all files and File records related to this video.  Delete this Video record.
        Add it to it's Channel's skip list."""
        self.file_group.delete()

        self.add_to_skip_list()
        session = Session.object_session(self)
        session.delete(self)

    def add_to_skip_list(self):
        """Add this video to it's Channel's skip list."""
        if self.channel and self.source_id:
            self.channel.add_video_to_skip_list(self.source_id)

    def set_viewed(self):
        self.viewed = now()

    def get_info_json(self) -> Optional[Dict]:
        """If this Video has an info_json file, return it's contents.  Otherwise, return None."""
        info_json_path = self.info_json_path
        if not info_json_path:
            return

        try:
            with info_json_path.open('rb') as fh:
                return json.load(fh)
        except FileNotFoundError:
            logger.warning(f'Unable to find info json file!  {info_json_path}')
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

    def validate(self):
        """Perform a validation of this video and it's files."""
        if not self.file_group.primary_path:
            # Can't validate if there is no video file.
            logger.error(f'Unable to validate video {self.id} without primary file!')

        from .lib import validate_video
        try:
            validate_video(self, self.channel.generate_posters if self.channel else False)
        except Exception as e:
            logger.warning(f'Failed to validate video {self}', exc_info=e)

        self.file_group.model = Video.__tablename__
        self.file_group.a_text = self.file_group.title
        self.file_group.c_text = self.get_video_description()
        # self.file_group.d_text is handled in `validate_video`.

    @staticmethod
    def from_paths(session: Session, *paths: pathlib.Path) -> 'Video':
        file_group = FileGroup.from_paths(session, *paths)

        # Video may have been downloaded previously.
        video = session.query(Video).filter(Video.file_group_id == file_group.id).one_or_none()
        if not video:
            video = Video(file_group=file_group)

        video.validate()
        session.add(video)
        session.flush([video, file_group])
        return video

    @property
    def info_json_file(self) -> Optional[dict]:
        for file in self.file_group.my_json_files():
            return file

    @property
    def info_json_path(self) -> Optional[pathlib.Path]:
        if info_json_file := self.info_json_file:
            return info_json_file['path']

    @property
    def video_path(self) -> Optional[pathlib.Path]:
        if self.file_group.primary_path:
            return self.file_group.primary_path

        # No primary file somehow, return the first video file.
        for file_group in self.file_group.my_video_files():
            return file_group['path']

    @property
    def poster_file(self) -> Optional[dict]:
        for file_group in self.file_group.my_poster_files():
            return file_group

    @property
    def poster_path(self) -> Optional[pathlib.Path]:
        if poster_file := self.poster_file:
            return poster_file['path']

    @property
    def caption_files(self) -> List[dict]:
        return self.file_group.my_files('text/srt') + self.file_group.my_files('text/vtt')

    @property
    def caption_paths(self) -> List[pathlib.Path]:
        return [i['path'] for i in self.caption_files]

    def get_caption_text(self) -> Optional[str]:
        """Search the FileGroup's files for a caption file.  Return the captions from only the best caption file."""
        caption_paths = self.caption_paths
        # Some SRT files are more supported than others, these are their preferred order.
        caption_text = None
        if english_srt := [i for i in caption_paths if i.name.endswith('.en.srt')]:
            caption_text = read_captions(english_srt[0])
        elif srt := [i for i in caption_paths if i.name.endswith('.srt')]:
            caption_text = read_captions(srt[0])
        elif english_vtt := [i for i in caption_paths if i.name.endswith('.en.vtt')]:
            caption_text = read_captions(english_vtt[0])
        elif vtt := [i for i in caption_paths if i.name.endswith('.vtt')]:
            caption_text = read_captions(vtt[0])

        return caption_text

    @staticmethod
    @optional_session
    def find_by_path(path, session: Session) -> Optional['Video']:
        video = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.primary_path == path).one_or_none()
        return video

    @staticmethod
    @optional_session
    def find_by_id(id_: int, session: Session) -> Optional['Video']:
        video = session.query(Video).filter(Video.id == id_).one_or_none()
        return video

    def add_tag(self, tag_or_tag_name: Union[Tag, str]) -> TagFile:
        tag = Tag.find_by_name(tag_or_tag_name) if isinstance(tag_or_tag_name, str) else tag_or_tag_name
        return self.file_group.add_tag(tag)


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

    info_json = deferred(Column(JSON))
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

        # URL should not be empty string.
        if 'url' in data:
            data['url'] = data['url'] or None

        for key, value in data.items():
            setattr(self, key, value)

        # We need an absolute directory.
        if isinstance(self.directory, pathlib.Path) and not self.directory.is_absolute():
            self.directory = get_media_directory() / self.directory
        elif isinstance(self.directory, str) and not pathlib.Path(self.directory).is_absolute():
            self.directory = get_media_directory() / self.directory

        # All channels with a URL and download_frequency should have a download.
        session: Session = Session.object_session(self)
        if download and not self.download_frequency:
            download_manager.delete_download(download.id, session)
        elif download and self.download_frequency:
            download.frequency = self.download_frequency
            download.url = self.url
            # Keep next_download if available.
            download.next_download = download.next_download or download_manager.calculate_next_download(download,
                                                                                                        session)
            download.sub_downloader = 'video'
        elif not download and self.download_frequency and self.url:
            download = Download(frequency=self.download_frequency, url=self.url,
                                downloader='video_channel',
                                sub_downloader='video',
                                )
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
        """Get statistics about this channel."""
        with get_db_curs() as curs:
            stmt = '''
                SELECT
                    SUM(size),
                    MAX(size),
                    COUNT(video.id)
                FROM video
                LEFT JOIN file_group fg on fg.id = video.file_group_id
                WHERE channel_id = %(id)s
            '''
            curs.execute(stmt, dict(id=self.id))
            size, largest_video, video_count = curs.fetchone()
        statistics = dict(
            video_count=video_count,
            size=size,
            largest_video=largest_video,
        )
        return statistics

    async def refresh_files(self, send_events: bool = True):
        """Refresh all files within this Channel's directory.  Mark this channel as refreshed."""
        logger.debug('Channel.refresh_files refresh_files')
        # Get this Channel's ID for later.  Refresh may take a long time.
        self_id = self.id

        # Refresh all files within this channel's directory first.
        await refresh_files([self.directory], send_events=send_events)

        # Apply any info_json (update view counts) second.
        from modules.videos.common import update_view_counts
        if PYTEST:
            await update_view_counts(self_id)
            self.refreshed = True
        else:

            # Perform info_json in background task.  Channel will be marked as refreshed after this completes.
            async def _():
                await update_view_counts(self_id)
                with get_db_session(commit=True) as session:
                    channel: Channel = session.query(Channel).filter(Channel.id == self_id).one()
                    channel.refreshed = True

            background_task(_())

    @staticmethod
    @optional_session
    def get_by_id(id_: int, session: Session = None) -> Optional['Channel']:
        channel = session.query(Channel).filter_by(id=id_).one_or_none()
        return channel
