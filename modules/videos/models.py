import json
import pathlib
from pathlib import Path
from typing import Optional, Dict, List, Union

from sqlalchemy import Column, Integer, String, Boolean, JSON, Date, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, Session, deferred
from sqlalchemy.orm.collections import InstrumentedList

from modules.videos.errors import UnknownVideo, UnknownChannel
from wrolpi.captions import read_captions
from wrolpi.common import Base, ModelHelper, logger, get_media_directory, background_task, replace_file
from wrolpi.db import get_db_curs, get_db_session, optional_session
from wrolpi.downloader import Download, download_manager, DownloadFrequency
from wrolpi.files.lib import refresh_files, split_path_stem_and_suffix
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile
from wrolpi.vars import PYTEST

logger = logger.getChild(__name__)

__all__ = ['Video', 'Channel', 'ChannelDownload']


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    id = Column(Integer, primary_key=True)

    source_id = Column(String)  # The id from yt-dlp
    view_count = Column(Integer)  # The view count from the ChannelDownloader (or from initial download)
    ffprobe_json = deferred(Column(JSON))  # Data that is fetched once from ffprobe (ffmpeg)
    have_comments = Column(Boolean, default=False)  # see `get_missing_videos_comments`
    comments_failed = Column(Boolean, default=False)  # see `get_missing_videos_comments`

    channel_id = Column(Integer, ForeignKey('channel.id'))
    channel = relationship('Channel', primaryjoin='Video.channel_id==Channel.id', back_populates='videos')
    file_group_id = Column(BigInteger, ForeignKey('file_group.id', ondelete='CASCADE'), unique=True, nullable=False)
    file_group: FileGroup = relationship('FileGroup')

    def __repr__(self):
        v = None
        if self.video_path:
            v = repr(str(self.video_path.relative_to(get_media_directory())))
        return f'<Video id={self.id} title={repr(self.file_group.title)} path={v} channel={self.channel_id} ' \
               f'source_id={repr(self.source_id)}>'

    def __json__(self) -> dict:
        d = self.file_group.__json__()

        channel = None
        if self.channel:
            channel = dict(id=self.channel.id, name=self.channel.name)

        codec_names = []
        codec_types = []

        try:
            if self.ffprobe_json:
                codec_names = [i['codec_name'] for i in self.ffprobe_json['streams']]
                codec_types = [i['codec_type'] for i in self.ffprobe_json['streams']]
        except Exception as e:
            logger.error(f'{self} ffprobe_json is invalid', exc_info=e)

        # TODO these are large objects.  Can they be fetched on demand?
        captions = self.file_group.d_text
        comments = self.get_comments()

        # Put live data in "video" instead of "data" to avoid confusion on the frontend.
        d['video'] = dict(
            caption=captions,
            caption_files=self.caption_files,
            channel=channel,
            channel_id=self.channel_id,
            codec_names=codec_names,
            codec_types=codec_types,
            comments=comments,
            comments_failed=self.comments_failed,
            description=self.file_group.c_text or self.get_video_description(),
            have_comments=self.have_comments,
            id=self.id,
            info_json_file=self.info_json_file,
            info_json_path=self.info_json_path,
            poster_file=self.poster_file,
            poster_path=self.poster_path,
            source_id=self.source_id,
            stem=split_path_stem_and_suffix(self.video_path)[0],
            video_path=self.video_path,
            view_count=self.view_count,
        )
        return d

    def delete(self, add_to_skip_list: bool = True):
        """Remove all files and File records related to this video.  Delete this Video record.
        Add it to it's Channel's skip list."""
        self.file_group.delete()

        if add_to_skip_list:
            self.add_to_skip_list()
        session = Session.object_session(self)
        session.delete(self)

    def add_to_skip_list(self):
        """Add this video to the DownloadManager's skip list."""
        if self.file_group.url:
            download_manager.add_to_skip_list(self.file_group.url)
        else:
            logger.warning(f'{self} cannot be added to skip list because it does not have a URL')

    def get_info_json(self) -> Optional[Dict]:
        """If this Video has an info_json file, return its contents.  Otherwise, return None."""
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
        if (info_json := self.get_info_json()) and (description := info_json.get('description')):
            return description

    def get_surrounding_videos(self):
        """
        Get the previous and next videos around this Video.  The videos must be in the same Channel.

        Example:
            >>> vid1 = Video(id=1, upload_date=10)
            >>> vid2 = Video(id=2, upload_date=20)
            >>> vid3 = Video(id=3, upload_date=30)

            >>> vid1.get_surrounding_videos()
            (None, vid2)
            >>> vid2.get_surrounding_videos()
            (vid1, vid3)
            >>> vid3.get_surrounding_videos()
            (vid2, None)
        """
        session = Session.object_session(self)

        with get_db_curs() as curs:
            if self.file_group.published_datetime:
                # Get videos next to this Video's upload date.
                stmt = '''
                        WITH numbered_videos AS (
                            SELECT fg.id AS fg_id, v.id AS v_id,
                                ROW_NUMBER() OVER (ORDER BY published_datetime ASC) AS row_number
                            FROM file_group fg
                            LEFT OUTER JOIN video v on fg.id = v.file_group_id
                            WHERE
                                v.channel_id = %(channel_id)s
                                AND fg.published_datetime IS NOT NULL
                        )
                        SELECT v_id
                        FROM numbered_videos
                        WHERE row_number IN (
                            SELECT row_number+i
                            FROM numbered_videos
                            CROSS JOIN (SELECT -1 AS i UNION ALL SELECT 0 UNION ALL SELECT 1) n
                            WHERE
                            fg_id = %(fg_id)s
                        )
                '''
            else:
                # No videos near this Video with upload dates, recommend the files next to this Video.
                # Only recommend videos in the same Channel (or similarly without a Channel).
                channel_where = 'WHERE v.channel_id = %(channel_id)s' if self.channel_id \
                    else 'WHERE v.channel_id IS NULL'
                stmt = f'''
                    WITH numbered_videos AS (
                        SELECT fg.id AS fg_id, v.id AS v_id, ROW_NUMBER() OVER (ORDER BY fg.primary_path) AS row_number
                        FROM
                            video v
                            LEFT JOIN file_group fg on fg.id = v.file_group_id
                        {channel_where}
                    )
                    SELECT v_id
                    FROM numbered_videos
                    WHERE row_number IN (
                        SELECT row_number+i
                        FROM numbered_videos
                        CROSS JOIN (SELECT -1 AS i UNION ALL SELECT 0 UNION ALL SELECT 1) n
                        WHERE fg_id = %(fg_id)s
                    )
                '''
            logger.debug(stmt)
            curs.execute(stmt, dict(channel_id=self.channel_id, fg_id=self.file_group_id))

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
        previous_video = Video.find_by_id(previous_id, session) if previous_id else None
        next_video = Video.find_by_id(next_id, session) if next_id else None

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
            if PYTEST:
                raise

        self.file_group.model = Video.__tablename__
        self.file_group.a_text = self.file_group.title
        self.file_group.c_text = self.get_video_description()
        # self.file_group.d_text is handled in `validate_video`.

        if (comments := self.get_comments()) and len(comments) >= 5:
            self.have_comments = True

    @staticmethod
    def from_paths(session: Session, *paths: pathlib.Path) -> 'Video':
        file_group = FileGroup.from_paths(session, *paths)

        # Video may have been downloaded previously.
        video = session.query(Video).filter(Video.file_group_id == file_group.id).one_or_none()
        if not video:
            video = Video(file_group=file_group)
        session.add(video)
        session.flush([video, file_group])

        video.validate()
        session.flush([video, ])
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
        return self.file_group.my_files('text/vtt') + self.file_group.my_files('text/srt') \
            + self.file_group.my_files('application/x-subrip')

    @property
    def caption_paths(self) -> List[pathlib.Path]:
        return [i['path'] for i in self.caption_files]

    def get_caption_text(self) -> Optional[str]:
        """Search the FileGroup's files for a caption file.  Return the captions from only the best caption file."""
        caption_paths = self.caption_paths
        # Some SRT files are more supported than others, these are their preferred order.
        caption_text = None
        if english_vtt := [i for i in caption_paths if i.name.endswith('.en.vtt')]:
            caption_text = read_captions(english_vtt[0])
        elif vtt := [i for i in caption_paths if i.name.endswith('.vtt')]:
            caption_text = read_captions(vtt[0])
        elif english_srt := [i for i in caption_paths if i.name.endswith('.en.srt')]:
            caption_text = read_captions(english_srt[0])
        elif srt := [i for i in caption_paths if i.name.endswith('.srt')]:
            caption_text = read_captions(srt[0])

        return caption_text

    @staticmethod
    @optional_session
    def get_by_path(path, session: Session) -> Optional['Video']:
        video = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.primary_path == path).one_or_none()
        return video

    @staticmethod
    @optional_session
    def get_by_url(url: str, session: Session) -> Optional['Video']:
        video = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.url == url).one_or_none()
        return video

    @staticmethod
    @optional_session
    def get_by_id(id_: int, session: Session = None) -> Optional['Video']:
        """Attempt to find a Video with the provided id.  Returns None if it cannot be found."""
        video = session.query(Video).filter(Video.id == id_).one_or_none()
        return video

    @staticmethod
    @optional_session
    def find_by_id(id_: int, session: Session = None) -> 'Video':
        """Find a Video with the provided id, raises an exception if it cannot be found.

        @raise UnknownVideo: if the Video can not be found"""
        video = Video.get_by_id(id_, session)
        if not video:
            raise UnknownVideo(f'Cannot find Video with id {id_}')
        return video

    def add_tag(self, tag_or_tag_name: Union[Tag, str], session: Session = None) -> TagFile:
        session = session or Session.object_session(self)
        tag = Tag.find_by_name(tag_or_tag_name) if isinstance(tag_or_tag_name, str) else tag_or_tag_name
        return self.file_group.add_tag(tag, session=session)

    async def get_ffprobe_json(self) -> dict:
        """Return the ffprobe json object if previously stored.

        Runs ffprobe if this data does not yet exist."""
        if not self.video_path:
            raise RuntimeError(f'Cannot get ffprobe json without video file: {self}')

        if not self.ffprobe_json:
            from modules.videos.common import ffprobe_json
            self.ffprobe_json = await ffprobe_json(self.video_path)
            self.flush()

        return self.ffprobe_json

    def get_streams_by_codec_name(self, codec_name: str) -> List[dict]:
        """Return all data about all streams which match the codec_name.

        >>> video = Video()
        >>> video.get_streams_by_codec_name('h264')
        [ {'codec_name': 'h264', ...} ]
        """
        if not self.ffprobe_json:
            raise RuntimeError(f'ffprobe data has not been extracted, call Video.get_ffprobe_json().')

        streams = [i for i in self.ffprobe_json['streams'] if i['codec_name'] == codec_name]
        return streams

    def get_streams_by_codec_type(self, codec_type: str) -> List[dict]:
        """Return all data about all streams which match the codec_type.

        >>> video = Video()
        >>> video.get_streams_by_codec_type('video')
        [ {'codec_type': 'video', ...} ]
        """
        if not self.ffprobe_json:
            raise RuntimeError(f'ffprobe data has not been extracted, call Video.get_ffprobe_json().')

        streams = [i for i in self.ffprobe_json['streams'] if i['codec_type'] == codec_type]
        return streams

    def detect_is_complete(self):
        from modules.videos.common import ffmpeg_video_complete
        return ffmpeg_video_complete(self.video_path)

    def get_channel_entry(self) -> Optional[Dict]:
        """Return the info_json entry for this Video from its Channel."""
        if self.channel and self.source_id:
            return self.channel.get_video_entry_by_id(self.source_id)

    @staticmethod
    async def delete_duplicate_videos(session: Session, url: str, source_id: str, video_path: pathlib.Path) -> bool:
        """Searches for Videos that share a `source_id` or `url`.  Attempts to keep the best video at `video_path`, then
        deletes the rest."""
        # Get all Videos that share the URL or the source_id.
        matching_videos_with_url = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.url == url) \
            .all()
        matching_videos_with_source_id = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.model == 'video', Video.source_id == source_id) \
            .all()
        duplicate_videos = list()
        for video in matching_videos_with_url:
            if video.id not in [i.id for i in duplicate_videos]:
                duplicate_videos.append(video)
        for video in matching_videos_with_source_id:
            if video.id not in [i.id for i in duplicate_videos]:
                duplicate_videos.append(video)

        # All the tags of all the files.
        tag_names = {i for j in duplicate_videos for i in j.file_group.tag_names}

        def delete_video(video_: Video):
            """Delete a Video with any of its tags."""
            for tag_name_ in video_.file_group.tag_names:
                tag_ = Tag.find_by_name(tag_name_)
                video_.file_group.remove_tag(tag_, session)
            video_.delete()

        changes = False
        # Delete any Videos without real files.
        missing_file_indexes = []
        for idx, video in enumerate(duplicate_videos):
            if not video.video_path.is_file():
                logger.debug(f'Deleting {video} because the video file does not exist')
                missing_file_indexes.append(idx)
                delete_video(video)
                changes = True
        duplicate_videos = [i for idx, i in enumerate(duplicate_videos) if idx not in missing_file_indexes]

        if len(duplicate_videos) < 2:
            # No duplicates.
            logger.debug(f'No duplicates to delete: {url=} {source_id=}')
            return changes

        # Order videos by oldest first, we should keep the oldest if all files are the same size.
        duplicate_videos = sorted(duplicate_videos, key=lambda i: i.file_group.primary_path.stat().st_mtime)

        # Find the largest video, if possible.  If all videos are the same size then rename the oldest.
        largest_video_idx = 0
        for idx, video in enumerate(duplicate_videos):
            if video.file_group.size > duplicate_videos[largest_video_idx].file_group.size:
                largest_video_idx = idx
        largest_video = duplicate_videos.pop(largest_video_idx)

        # Delete the video at the destination, if it is not the largest.
        existing_video = Video.get_by_path(video_path, session=session)
        if existing_video and largest_video != existing_video:
            delete_video(existing_video)
            for idx, video in enumerate(duplicate_videos):
                if video == existing_video:
                    duplicate_videos.pop(idx)

        # Rename the video, add any missing tag names.
        if largest_video.video_path != video_path:
            largest_video.file_group.move(video_path)
        for tag_name in tag_names:
            if tag_name not in largest_video.file_group.tag_names:
                largest_video.add_tag(tag_name, session)

        logger.warning(f'Deleting duplicate videos: {duplicate_videos}')

        # Remove tags from all videos, delete all videos.
        for video in duplicate_videos:
            delete_video(video)

        return True

    @property
    def location(self) -> str:
        """The href of the video in the App."""
        if not self.id:
            raise RuntimeError('Video id not set.  Flush to DB.')

        if self.channel_id:
            return f'/videos/channel/{self.channel_id}/video/{self.id}'
        return f'/videos/video/{self.id}'

    def get_comments(self):
        return (self.get_info_json() or dict()).get('comments')

    def replace_info_json(self, info_json: dict):
        """Replace the info json file with the new json dict.  Handles adding new info_json file, if necessary."""
        info_json_path = self.info_json_path or self.video_path.with_suffix('.info.json')
        info_json = json.dumps(info_json, indent=2)
        replace_file(info_json_path, info_json, missing_ok=True)

        if not self.info_json_path:
            self.file_group.append_files(info_json_path)


class ChannelDownload(Base):
    """One-to-many join table between Channel and Download.  Expects to link using Download.url."""
    __tablename__ = 'channel_download'
    channel_id = Column(Integer, ForeignKey('channel.id'), primary_key=True)
    channel = relationship('Channel', primaryjoin='ChannelDownload.channel_id==Channel.id',
                           back_populates='channel_downloads')
    download_url = Column(String, ForeignKey('download.url'), primary_key=True)
    download = relationship('Download', primaryjoin='ChannelDownload.download_url==Download.url')

    def __repr__(self):
        return f'<ChannelDownload url={self.download_url} channel_id={self.channel_id}>'

    def __json__(self) -> dict:
        d = self.download.__json__()
        d['channel_id'] = self.channel_id
        return d

    @staticmethod
    def get_by_id(id: int, session: Session) -> Optional['ChannelDownload']:
        return session.query(ChannelDownload).filter(ChannelDownload.channel_id == id).one_or_none()

    @staticmethod
    def get_by_url(url: str, session: Session) -> Optional['ChannelDownload']:
        return session.query(ChannelDownload).filter(ChannelDownload.download_url == url).one_or_none()

    def delete(self):
        session = Session.object_session(self)
        if self.download:
            self.download.delete(skip=False)
        session.delete(self)


class Channel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String, unique=True)  # will only be downloaded if ChannelDownload exists.
    directory: pathlib.Path = Column(MediaPathType)
    generate_posters = Column(Boolean, default=False)  # generating posters may delete files, and can be slow.
    calculate_duration = Column(Boolean, default=True)  # use ffmpeg to extract duration (slower than info json).
    source_id = Column(String)  # the ID from the source website.
    refreshed = Column(Boolean, default=False)  # The files in the Channel have been refreshed.

    info_json = deferred(Column(JSON))
    info_date = Column(Date)

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')
    channel_downloads: InstrumentedList = \
        relationship('ChannelDownload', primaryjoin='ChannelDownload.channel_id==Channel.id')

    def __repr__(self):
        return f'<Channel id={self.id} name={repr(self.name)} url={self.url} directory={self.directory}>'

    def delete_with_videos(self):
        """Delete all Video records (but not video files) related to this Channel.  Then delete the Channel."""
        session = Session.object_session(self)

        # Disown the videos.
        videos = session.query(Video).filter_by(channel_id=self.id)
        for video in videos:
            video.channel = None

        for cd in self.channel_downloads:
            cd: ChannelDownload
            cd.delete()

        # Must commit before final deletion.
        # TODO why?
        session.commit()
        session.delete(self)

    def update(self, data: dict):
        """
        Update the attributes of this Channel.  Will also update the Channel's Download, if it has one.
        """
        data = data.copy()

        # URL should not be empty string.
        if 'url' in data:
            data['url'] = data['url'] or None

        channel_downloads = data.pop('channel_downloads', [])

        for key, value in data.items():
            setattr(self, key, value)

        # We need an absolute directory.
        if isinstance(self.directory, pathlib.Path) and not self.directory.is_absolute():
            self.directory = get_media_directory() / self.directory
        elif isinstance(self.directory, str) and not pathlib.Path(self.directory).is_absolute():
            self.directory = get_media_directory() / self.directory

        session: Session = Session.object_session(self)

        for cd in channel_downloads:
            # `cd` may be string from config file.
            url = cd['url'] if isinstance(cd, dict) else cd
            cd_ = ChannelDownload.get_by_url(url, session=session)
            if not cd_:
                cd_ = self.get_or_create_download(url, session=session)
            # If `cd` is dict, use that frequency.  Try to keep the currently set frequency, finally 30 days.
            frequency = cd['frequency'] if isinstance(cd, dict) else cd_.download.frequency or DownloadFrequency.days30
            cd_.download.frequency = frequency

        session.flush()

    def config_view(self) -> dict:
        """
        Retrieve the data about this Channel that should be stored in a config file.
        """
        config = dict(
            calculate_duration=self.calculate_duration,
            directory=str(self.directory),
            generate_posters=self.generate_posters,
            name=self.name,
            source_id=self.source_id,
            url=self.url or None,
            channel_downloads=[i.download_url for i in self.channel_downloads]
        )
        return config

    def get_relative_path(self, path: Path, exists: bool = True):
        path = self.directory / path
        if exists and not path.exists():
            raise FileNotFoundError(f'{path} does not exist!')
        return path

    @staticmethod
    def get_by_path(path: pathlib.Path, session: Session) -> Optional['Channel']:
        return session.query(Channel).filter_by(directory=path).one_or_none()

    def __json__(self) -> dict:
        d = dict(
            channel_downloads=self.channel_downloads,
            directory=self.directory,
            id=self.id,
            name=self.name,
            url=self.url,
        )
        return d

    def dict(self, with_statistics: bool = False, with_downloads: bool = True) -> dict:
        d = super(Channel, self).dict()
        d['directory'] = self.directory.relative_to(get_media_directory()) if self.directory else None
        if with_statistics:
            d['statistics'] = self.get_statistics()
        if with_downloads:
            d['channel_downloads'] = self.channel_downloads
        return d

    def get_statistics(self):
        """Get statistics about this channel."""
        with get_db_curs() as curs:
            stmt = '''
                SELECT
                    SUM(size),
                    MAX(size),
                    COUNT(video.id),
                    SUM(fg.length)
                FROM video
                LEFT JOIN file_group fg on fg.id = video.file_group_id
                WHERE channel_id = %(id)s
            '''
            curs.execute(stmt, dict(id=self.id))
            size, largest_video, video_count, length = curs.fetchone()
        statistics = dict(
            video_count=video_count,
            size=size,
            largest_video=largest_video,
            length=length,
        )
        return statistics

    async def refresh_files(self, send_events: bool = True):
        """Refresh all files within this Channel's directory.  Mark this channel as refreshed."""
        logger.debug(f'{self}.refresh_files')
        # Get this Channel's ID for later.  Refresh may take a long time.
        self_id = self.id

        # Refresh all files within this channel's directory first.
        await refresh_files([self.directory], send_events=send_events)

        # Apply any info_json (update view counts) second.
        from modules.videos.common import update_view_counts_and_censored
        if PYTEST:
            await update_view_counts_and_censored(self_id)
            self.refreshed = True
        else:

            # Perform info_json in background task.  Channel will be marked as refreshed after this completes.
            async def _():
                await update_view_counts_and_censored(self_id)
                with get_db_session(commit=True) as session:
                    channel: Channel = session.query(Channel).filter(Channel.id == self_id).one()
                    channel.refreshed = True

            background_task(_())

    @staticmethod
    @optional_session
    def get_by_id(id_: int, session: Session = None) -> Optional['Channel']:
        """Attempt to find a Channel with the provided id.  Returns None if it cannot be found."""
        channel = session.query(Channel).filter_by(id=id_).one_or_none()
        return channel

    @staticmethod
    @optional_session
    def find_by_id(id_: int, session: Session = None) -> 'Channel':
        """Find a Channel with the provided id, raises an exception when no Channel is found.

        @raise UnknownChannel: if the channel can not be found"""
        channel = Channel.get_by_id(id_, session=session)
        if not channel:
            raise UnknownChannel(f'Cannot find channel with id {id_}')
        return channel

    def get_video_entry_by_id(self, video_source_id: str) -> Optional[Dict]:
        """Search my info_json for the entry with the provided id."""
        if self.info_json:
            matching_entries = [i for i in self.info_json['entries'] if i['id'] == video_source_id]
            if len(matching_entries) == 1:
                return matching_entries[0]
            elif len(matching_entries) > 1:
                raise RuntimeError(f'More than one info_json entry matches {video_source_id}')

    def get_download(self, url: str = None, download_id: int = None) -> Optional[ChannelDownload]:
        """Attempt to get the ChannelDownload that matches the provided parameters."""
        if not url and not download_id:
            raise RuntimeError('Must provide either url or download_id')

        for cd in self.channel_downloads:
            if download_id and cd.download.id == download_id:
                return cd
            if url and cd.download.url == url:
                return cd

    @optional_session
    def get_or_create_download(self, url: str, session: Session = None, reset_attempts: bool = False) \
            -> ChannelDownload:
        """Get a ChannelDownload record, if it does not exist, create it.  Create a Download if necessary
        which goes into this Channel's directory."""
        from modules.videos.downloader import ChannelDownloader, VideoDownloader

        if not url:
            raise RuntimeError(f'Cannot get ChannelDownload without url')

        cd = ChannelDownload.get_by_url(url, session)
        if not cd:
            # A Channel is downloaded using the ChannelDownloader first.  Then, any missing videos are passed to
            # VideoDownloader.
            download = session.query(Download).filter_by(url=url).one_or_none()
            if not download:
                download = download_manager.create_download(url, ChannelDownloader.name, session=session,
                                                            sub_downloader_name=VideoDownloader.name,
                                                            reset_attempts=reset_attempts,
                                                            )
            # Download into this Channel's directory by default.
            destination = (download.settings or dict()).get('destination')
            if not destination:
                settings = (download.settings or dict())
                settings.update(dict(destination=str(self.directory)))
                download.settings = settings
            # Link between Channel and Download.
            cd = ChannelDownload.get_by_url(url, session)
            if not cd:
                cd = ChannelDownload(channel_id=self.id, download_url=url)
                session.add(cd)
            logger.debug(f'Created {cd} for {self}')

        return cd

    def get_rss_url(self) -> str | None:
        """Return the RSS Feed URL for this Channel, if any is possible."""
        if self.url and self.source_id and 'youtube.com' in self.url:
            return f'https://www.youtube.com/feeds/videos.xml?channel_id={self.source_id}'
