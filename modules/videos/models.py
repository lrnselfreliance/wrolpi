import json
import pathlib
from typing import Optional, Dict, List

from sqlalchemy import Column, Integer, String, Boolean, JSON, Date, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, Session, deferred
from sqlalchemy.orm.collections import InstrumentedList

from modules.videos.errors import UnknownVideo, UnknownChannel
from wrolpi import flags
from wrolpi.captions import read_captions
from wrolpi.common import Base, ModelHelper, logger, get_media_directory, background_task, replace_file, \
    unique_by_predicate
from wrolpi.db import get_db_curs, get_db_session, optional_session
from wrolpi.downloader import Download, download_manager, save_downloads_config
from wrolpi.errors import InvalidDownload
from wrolpi.events import Events
from wrolpi.files.lib import refresh_files, split_path_stem_and_suffix, move
from wrolpi.files.models import FileGroup
from wrolpi.media_path import MediaPathType
from wrolpi.tags import Tag, TagFile, save_tags_config
from wrolpi.vars import PYTEST, VIDEO_INFO_JSON_KEYS_TO_CLEAN

logger = logger.getChild(__name__)

__all__ = ['Video', 'Channel']


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

        # Put live data in "video" instead of "data" to avoid confusion on the frontend.
        d['video'] = dict(
            caption_files=self.caption_files,
            channel=channel,
            channel_id=self.channel_id,
            codec_names=codec_names,
            codec_types=codec_types,
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
        self.file_group.delete(add_to_skip_list=add_to_skip_list)
        session = Session.object_session(self)
        session.delete(self)

    @staticmethod
    def can_model(file_group: FileGroup) -> bool:
        return file_group.mimetype.startswith('video/')

    @staticmethod
    def do_model(file_group: FileGroup, session: Session) -> 'Video':
        video = Video(file_group_id=file_group.id, file_group=file_group)
        session.add(video)
        video.validate()
        file_group.indexed = True
        video.flush()
        return video

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
                       WITH numbered_videos AS (SELECT fg.id                                               AS fg_id,
                                                       v.id                                                AS v_id,
                                                       ROW_NUMBER() OVER (ORDER BY published_datetime ASC) AS row_number
                                                FROM file_group fg
                                                         LEFT OUTER JOIN video v on fg.id = v.file_group_id
                                                WHERE v.channel_id = %(channel_id)s
                                                  AND fg.published_datetime IS NOT NULL)
                       SELECT v_id
                       FROM numbered_videos
                       WHERE row_number IN (SELECT row_number + i
                                            FROM numbered_videos
                                                     CROSS JOIN (SELECT -1 AS i UNION ALL SELECT 0 UNION ALL SELECT 1) n
                                            WHERE fg_id = %(fg_id)s) \
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

    def validate(self, session: Session = None):
        """Perform a validation of this video and it's files."""
        if not self.file_group.primary_path:
            # Can't validate if there is no video file.
            logger.error(f'Unable to validate video {self.id} without primary file!')

        logger.debug(f'Validating {self}')
        from .lib import validate_video
        try:
            validate_video(self, self.channel.generate_posters if self.channel else False)
        except Exception as e:
            logger.error(f'Failed to validate video {self}', exc_info=e)
            if PYTEST:
                raise

        self.file_group.model = Video.__tablename__
        self.file_group.a_text = self.file_group.title
        self.file_group.c_text = self.get_video_description()
        # self.file_group.d_text is handled in `validate_video`.

        if (comments := self.get_comments()) and len(comments) >= 5:
            logger.debug(f'{self} has comments')
            self.have_comments = True

        # If this Video is in a Channel's directory, then it is part of that Channel.
        session: Session = session or Session.object_session(self)
        if session and (channel := Channel.get_by_path(self.video_path.parent, session)):
            self.channel = channel
            logger.debug(f'{self} has Channel {channel}')

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

    def add_tag(self, tag_id_or_name: int | str, session: Session = None) -> TagFile:
        session = session or Session.object_session(self)
        return self.file_group.add_tag(tag_id_or_name, session=session)

    def untag(self, tag_id_or_name: int | str, session: Session = None):
        session = session or Session.object_session(self)
        self.file_group.untag(tag_id_or_name, session)

    async def get_ffprobe_json(self) -> dict:
        """Return the ffprobe json object if previously stored.

        Runs ffprobe if this data does not yet exist."""
        if not self.video_path:
            raise RuntimeError(f'Cannot get ffprobe json without video file: {self}')

        if not self.ffprobe_json:
            from modules.videos.common import ffprobe_json
            self.ffprobe_json = await ffprobe_json(self.video_path)

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
                video_.file_group.untag(tag_name_, session)
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

    def get_comments(self) -> list | None:
        return (self.get_info_json() or dict()).get('comments')

    def clean_info_json(self, info_json_contents: dict = None) -> dict | None:
        """Remove large and mostly useless data in the info_json."""
        info_json_contents = info_json_contents or self.get_info_json()
        if info_json_contents:
            for key in VIDEO_INFO_JSON_KEYS_TO_CLEAN:
                info_json_contents.pop(key, None)
        return info_json_contents

    def replace_info_json(self, info_json: dict, clean: bool = True, format_: bool = True):
        """Replace the info json file with the new json dict.  Handles adding new info_json file, if necessary."""
        info_json_path = self.info_json_path or self.video_path.with_suffix('.info.json')
        if clean:
            info_json = self.clean_info_json(info_json)

        if format_:
            info_json = json.dumps(info_json, indent=2, sort_keys=True)
        else:
            info_json = json.dumps(info_json)

        replace_file(info_json_path, info_json, missing_ok=True)

        if not self.info_json_path:
            self.file_group.append_files(info_json_path)


class Channel(ModelHelper, Base):
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String, unique=True)  # will only be downloaded if related Download exists.
    directory: pathlib.Path = Column(MediaPathType)
    generate_posters = Column(Boolean, default=False)  # generating posters may delete files, and can be slow.
    calculate_duration = Column(Boolean, default=True)  # use ffmpeg to extract duration (slower than info json).
    download_missing_data = Column(Boolean, default=True)  # fetch missing data like `source_id` and video comments.
    source_id = Column(String)  # the ID from the source website.
    refreshed = Column(Boolean, default=False)  # The files in the Channel have been refreshed.

    # Columns updated by triggers
    video_count = Column(Integer, default=0)  # update_channel_video_count
    total_size = Column(Integer, default=0)  # update_channel_size
    minimum_frequency = Column(Integer)  # update_channel_minimum_frequency

    info_json = deferred(Column(JSON))
    info_date = Column(Date)

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')
    downloads: InstrumentedList = relationship('Download', primaryjoin='Download.channel_id==Channel.id')
    tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'))
    tag = relationship('Tag', primaryjoin='Channel.tag_id==Tag.id')

    def __repr__(self):
        return f'<Channel id={self.id} name={repr(self.name)} url={self.url} directory={self.directory}>'

    @property
    def tag_name(self) -> str | None:
        return self.tag.name if self.tag else None

    @property
    def location(self) -> str:
        return f'/videos/channel/{self.id}/video'

    @property
    def info_json_path(self) -> pathlib.Path:
        if self.directory:
            if not self.directory.exists():
                self.directory.mkdir(parents=True)
            return self.directory / f'{self.name}.info.json'

        raise FileNotFoundError(f'Cannot create Channel info json because directory is not defined: {self}')

    def delete_with_videos(self):
        """Delete all Video records (but not video files) related to this Channel.  Then delete the Channel."""
        session = Session.object_session(self)

        # Disown the videos.
        videos = session.query(Video).filter_by(channel_id=self.id)
        for video in videos:
            video.channel = None

        for download in self.downloads:
            download: Download
            download.delete()

        # Must commit before final deletion.
        session.delete(self)

    def update(self, data: dict):
        """
        Update the attributes of this Channel.  Will also update the Channel's Download, if it has one.
        """
        channel_id = self.id
        data = data.copy()

        # URL should not be empty string.
        url = data.pop('url')
        self.url = url or None

        session: Session = Session.object_session(self)

        downloads = data.pop('downloads', [])

        if tag_name := data.pop('tag_name', None):
            self.tag = Tag.find_by_name(tag_name, session)

        for key, value in data.items():
            setattr(self, key, value)

        # We need an absolute directory.
        if isinstance(self.directory, pathlib.Path) and not self.directory.is_absolute():
            self.directory = get_media_directory() / self.directory
        elif isinstance(self.directory, str) and not pathlib.Path(self.directory).is_absolute():
            self.directory = get_media_directory() / self.directory

        for download in downloads:
            url = None
            frequency = None
            if isinstance(download, dict):
                url = download['url']
                # Use download frequency from downloads config before the channels config.
                if existing_download := Download.get_by_url(url, session=session):
                    frequency = existing_download.frequency
                else:
                    frequency = download.get('frequency')
            elif isinstance(download, Download):
                url = download.url
                frequency = download.frequency

            if not url:
                raise RuntimeError(f'Unknown download type: {download}')
            if not frequency:
                logger.error(f'Refusing to create Download for Channel without frequency: {url}')
                continue

            download = self.get_or_create_download(url, frequency, session=session, reset_attempts=True)
            download.channel_id = channel_id
            session.add(download)

    def config_view(self) -> dict:
        """
        Retrieve the data about this Channel that should be stored in a config file.
        """
        config = dict(
            calculate_duration=self.calculate_duration,
            directory=str(self.directory),
            download_missing_data=self.download_missing_data,
            downloads=[{'url': i.url, 'frequency': i.frequency} for i in self.downloads],
            generate_posters=self.generate_posters,
            name=self.name,
            source_id=self.source_id,
            tag_name=self.tag_name,
            url=self.url or None,
        )
        return config

    @staticmethod
    def get_by_path(path: pathlib.Path, session: Session) -> Optional['Channel']:
        if not path:
            raise RuntimeError('Must provide path to get Channel')
        path = pathlib.Path(path) if isinstance(path, str) else path
        path = str(path.absolute()) if path.is_absolute() else str(get_media_directory() / path)
        channel = session.query(Channel).filter_by(directory=path).one_or_none()
        return channel

    def __json__(self) -> dict:
        d = dict(
            directory=self.directory,
            downloads=self.downloads,
            id=self.id,
            name=self.name,
            tag_name=self.tag_name,
            url=self.url,
        )
        return d

    def dict(self, with_statistics: bool = False, with_downloads: bool = True) -> dict:
        d = super(Channel, self).dict()
        d['tag_name'] = self.tag_name
        d['rss_url'] = self.get_rss_url()
        d['directory'] = \
            self.directory.relative_to(get_media_directory()) if self.directory else None
        if with_statistics:
            d['statistics'] = self.get_statistics()
        if with_downloads:
            d['downloads'] = self.downloads
        return d

    def get_statistics(self):
        """Get statistics about this channel."""
        with get_db_curs() as curs:
            stmt = '''
                   SELECT SUM(size)                                                     AS "size",
                          MAX(size)                                                     AS "largest_video",
                          COUNT(video.id)                                               AS "video_count",
                          SUM(fg.length)                                                AS "length",
                          -- Videos may use multiple tags.
                          COUNT(video.id) FILTER ( WHERE tf.file_group_id IS NOT NULL ) AS "video_tags"
                   FROM video
                            LEFT JOIN file_group fg on fg.id = video.file_group_id
                            LEFT JOIN public.tag_file tf on fg.id = tf.file_group_id
                   WHERE channel_id = %(id)s \
                   '''
            curs.execute(stmt, dict(id=self.id))
            return dict(curs.fetchone())

    def set_tag(self, tag_id_or_name: int | str | None) -> Tag | None:
        """Change the Tag relationship of this Channel.  Will clear the Tag if provided with None."""
        session = Session.object_session(self)
        if tag_id_or_name is None:
            # Clear tag.
            self.tag = None
        elif isinstance(tag_id_or_name, int):
            self.tag = Tag.find_by_id(tag_id_or_name, session)
        elif isinstance(tag_id_or_name, str):
            self.tag = Tag.find_by_name(tag_id_or_name, session)
        # Copy the id in case some code needs the id before flush.
        self.tag_id = self.tag.id if self.tag else None
        return self.tag

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
        if channel := Channel.get_by_id(id_, session=session):
            return channel
        raise UnknownChannel(f'Cannot find channel with id {id_}')

    def get_video_entry_by_id(self, video_source_id: str) -> Optional[Dict]:
        """Search my info_json for the entry with the provided id."""
        if self.info_json:
            matching_entries = [i for i in self.info_json['entries'] if i['id'] == video_source_id]
            if len(matching_entries) == 1:
                return matching_entries[0]
            elif len(matching_entries) > 1:
                raise RuntimeError(f'More than one info_json entry matches {video_source_id}')

    @optional_session
    def get_or_create_download(self, url: str, frequency: int, session: Session = None,
                               reset_attempts: bool = False) -> Download:
        """Get a Download record, if it does not exist, create it.  Create a Download if necessary
        which goes into this Channel's directory.
        """
        if not isinstance(url, str) or not url:
            raise InvalidDownload(f'Cannot get Download without url')
        if not frequency:
            raise InvalidDownload('Download for Channel must have a frequency')

        from modules.videos.downloader import ChannelDownloader, VideoDownloader

        download = Download.get_by_url(url, session=session)
        if not download:
            download = download_manager.recurring_download(url, frequency, ChannelDownloader.name, session=session,
                                                           sub_downloader_name=VideoDownloader.name,
                                                           destination=self.directory,
                                                           reset_attempts=reset_attempts,
                                                           )
        if reset_attempts:
            download.attempts = 0
        download.channel_id = self.id

        return download

    def get_rss_url(self) -> str | None:
        """Return the RSS Feed URL for this Channel, if any is possible."""
        yt_url = 'youtube.com' in self.url if self.url else False
        yt_source_id = self.source_id.startswith('UC') if self.source_id else False
        if yt_url and yt_source_id:
            return f'https://www.youtube.com/feeds/videos.xml?channel_id={self.source_id}'

    @staticmethod
    @optional_session
    def get_by_url(url: str, session: Session = None) -> Optional['Channel']:
        if not url:
            raise RuntimeError('Must provide URL to get Channel')
        channel = session.query(Channel).filter_by(url=url).one_or_none()
        return channel

    def format_directory(self, tag_name: str) -> pathlib.Path:
        from modules.videos.lib import format_videos_destination
        return format_videos_destination(self.name, tag_name, self.url)

    async def move_channel(self, directory: pathlib.Path, session: Session, send_events: bool = False):
        """Move the files of this Channel into a new directory."""
        if not directory.is_dir():
            raise FileNotFoundError(f'Destination directory does not exist: {directory}')

        old_directory = self.directory
        self.directory = directory

        def change_download_destinations(from_directory: pathlib.Path, to_directory: pathlib.Path):
            downloads = list(self.downloads)
            downloads.extend(Download.get_all_by_destination(from_directory))
            downloads = unique_by_predicate(downloads, lambda i: i.id)
            for download in downloads:
                download.destination = to_directory
            session.flush(downloads)

        # Only one tag can be moved at a time.
        with flags.refreshing:
            # Change destination of all Downloads of this Channel, or any Downloads which download into this Channel's
            # directory.
            change_download_destinations(old_directory, directory)

            session.commit()

            # Save configs before move, this is because move imports configs.
            from modules.videos.lib import save_channels_config
            save_downloads_config.activate_switch()
            save_channels_config.activate_switch()
            save_tags_config.activate_switch()

            # Move the contents of the Channel directory into the destination directory.
            logger.info(f'Moving {self} from {repr(str(old_directory))}')

        try:
            if not old_directory.exists():
                # Old directory does not exist, maintainer must have moved the Channel manually.
                if PYTEST:
                    await refresh_files([old_directory, directory])
                else:
                    background_task(refresh_files([old_directory, directory]))
                if send_events:
                    Events.send_file_move_completed(f'Channel {repr(self.name)} was moved, but Tags were lost')
            else:
                # `move` also uses `flags.refreshing`
                await move(directory, *list(old_directory.iterdir()))
                if send_events:
                    Events.send_file_move_completed(f'Channel {repr(self.name)} was moved')
        except Exception as e:
            logger.error(f'Channel move failed!  Reverting changes...', exc_info=e)
            # Downloads must be moved back to the old directory.
            change_download_destinations(directory, old_directory)
            self.directory = old_directory
            self.flush(session)
            if send_events:
                Events.send_file_move_failed(f'Moving Channel {self.name} has failed')
            raise
        finally:
            session.commit()
            if old_directory.exists() and not next(iter(old_directory.iterdir()), None):
                # Old directory is empty, delete it.
                old_directory.rmdir()

    @staticmethod
    def get_by_source_id(session: Session, source_id: str) -> Optional['Channel']:
        return session.query(Channel).filter_by(source_id=source_id).one_or_none()
