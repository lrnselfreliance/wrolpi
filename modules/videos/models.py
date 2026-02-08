import json
import pathlib
from typing import Optional, Dict, List

from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, BigInteger, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Session, deferred
from sqlalchemy.orm.collections import InstrumentedList

from modules.videos.errors import UnknownVideo, UnknownChannel
from wrolpi.captions import read_captions
from wrolpi.common import Base, ModelHelper, logger, get_media_directory, get_relative_to_media_directory, \
    background_task, replace_file
from wrolpi.db import get_db_curs, get_db_session
from wrolpi.downloader import Download
from wrolpi.files.lib import split_path_stem_and_suffix
from wrolpi.files.worker import file_worker
from wrolpi.files.models import FileGroup
from wrolpi.tags import Tag, TagFile
from wrolpi.vars import PYTEST, VIDEO_INFO_JSON_KEYS_TO_CLEAN

logger = logger.getChild(__name__)

__all__ = ['Video', 'Channel']


class Video(ModelHelper, Base):
    __tablename__ = 'video'
    __table_args__ = (
        Index('video_channel_id_idx', 'channel_id'),
        Index('video_source_id_idx', 'source_id'),
        Index('video_view_count_idx', 'view_count'),
    )
    id = Column(Integer, primary_key=True)

    source_id = Column(String)  # The id from yt-dlp
    view_count = Column(Integer)  # The view count from the ChannelDownloader (or from initial download)
    ffprobe_json = deferred(Column(JSONB))  # Data that is fetched once from ffprobe (ffmpeg)
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
    def do_model(session: Session, file_group: FileGroup) -> 'Video':
        # Check if a Video already exists for this FileGroup
        video = session.query(Video).filter_by(file_group_id=file_group.id).one_or_none()
        if not video:
            # Create new Video if it doesn't exist
            video = Video(file_group_id=file_group.id, file_group=file_group)
            session.add(video)
        video.validate(session)
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
        previous_video = Video.find_by_id(session, previous_id) if previous_id else None
        next_video = Video.find_by_id(session, next_id) if next_id else None

        return previous_video, next_video

    def validate(self, session: Session):
        """Perform a validation of this video and it's files."""
        if not self.file_group.primary_path:
            # Can't validate if there is no video file.
            logger.error(f'Unable to validate video {self.id} without primary file!')

        logger.debug(f'Validating {self}')

        # Look up the channel FIRST so we can use channel settings (like generate_posters)
        # during validation. Channel.get_by_path walks up the directory tree to find
        # channels even when videos are in subdirectories (e.g., year subdirs).
        session: Session = session or Session.object_session(self)
        if session and not self.channel and (channel := Channel.get_by_path(session, self.video_path.parent)):
            self.channel = channel
            logger.debug(f'{self} has Channel {channel}')

        from .lib import validate_video
        try:
            validate_video(session, self, self.channel.generate_posters if self.channel else False)
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

        # Set FileGroup.data with cached file paths (stored as relative filenames)
        # Paths are resolved to absolute when accessed via file_group.resolve_path()
        self.file_group.data = {
            'id': self.id,
            'video_path': self.video_path.name if self.video_path else None,
            'info_json_path': self.info_json_path.name if self.info_json_path else None,
            'poster_path': self.poster_path.name if self.poster_path else None,
            'caption_paths': [p.name for p in self.caption_paths] if self.caption_paths else [],
        }

    @staticmethod
    def from_paths(session: Session, *paths: pathlib.Path) -> 'Video':
        file_group = FileGroup.from_paths(session, *paths)

        # Video may have been downloaded previously.
        video = session.query(Video).filter(Video.file_group_id == file_group.id).one_or_none()
        if not video:
            video = Video(file_group=file_group)
        session.add(video)
        session.flush([video, file_group])

        video.validate(session)
        session.flush([video, ])
        return video

    @property
    def info_json_file(self) -> Optional[dict]:
        for file in self.file_group.my_json_files():
            # Only return .info.json files, not .ffprobe.json or other JSON files
            if file['path'].name.endswith('.info.json'):
                return file

    @property
    def info_json_path(self) -> Optional[pathlib.Path]:
        if info_json_file := self.info_json_file:
            return info_json_file['path']

    @property
    def ffprobe_json_path(self) -> Optional[pathlib.Path]:
        """Return the path to the .ffprobe.json file for this video."""
        if self.video_path:
            return self.video_path.with_suffix('.ffprobe.json')

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
    def get_by_path(session: Session, path) -> Optional['Video']:
        video = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.primary_path == path).one_or_none()
        return video

    @staticmethod
    def get_by_url(session: Session, url: str) -> Optional['Video']:
        video = session.query(Video) \
            .join(FileGroup, FileGroup.id == Video.file_group_id) \
            .filter(FileGroup.url == url).one_or_none()
        return video

    @staticmethod
    def get_by_id(session: Session, id_: int) -> Optional['Video']:
        """Attempt to find a Video with the provided id.  Returns None if it cannot be found."""
        video = session.query(Video).filter(Video.id == id_).one_or_none()
        return video

    @staticmethod
    def find_by_id(session: Session, id_: int) -> 'Video':
        """Find a Video with the provided id, raises an exception if it cannot be found.

        @raise UnknownVideo: if the Video can not be found"""
        video = Video.get_by_id(session, id_)
        if not video:
            raise UnknownVideo(f'Cannot find Video with id {id_}')
        return video

    def add_tag(self, session: Session, tag_id_or_name: int | str) -> TagFile:
        return self.file_group.add_tag(session, tag_id_or_name)

    def untag(self, session: Session, tag_id_or_name: int | str):
        self.file_group.untag(session, tag_id_or_name)

    async def get_ffprobe_json(self) -> dict:
        """Return the ffprobe json object if previously stored.

        Checks for cached .ffprobe.json file before running ffprobe.
        Runs ffprobe if no cached data exists."""
        if not self.video_path:
            raise RuntimeError(f'Cannot get ffprobe json without video file: {self}')

        # 1. Return from DB if already stored
        if self.ffprobe_json:
            return self.ffprobe_json

        from modules.videos.common import ffprobe_json, read_ffprobe_json_file, write_ffprobe_json_file

        # 2. Check if .ffprobe.json file exists
        ffprobe_path = self.ffprobe_json_path
        if ffprobe_path and ffprobe_path.is_file():
            cached_data = read_ffprobe_json_file(ffprobe_path)
            if cached_data:
                self.ffprobe_json = cached_data
                return self.ffprobe_json

        # 3. Run ffprobe and cache the result
        self.ffprobe_json = await ffprobe_json(self.video_path)
        if ffprobe_path:
            # Check if saving ffprobe json files is enabled
            from wrolpi.common import get_wrolpi_config
            if get_wrolpi_config().save_ffprobe_json:
                try:
                    write_ffprobe_json_file(ffprobe_path, self.ffprobe_json)
                    # Add the new file to the FileGroup so it's tracked
                    self.file_group.append_files(ffprobe_path)
                except IOError as e:
                    logger.warning(f'Failed to write ffprobe json cache file {ffprobe_path}', exc_info=e)

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
        existing_video = Video.get_by_path(session, video_path)
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
                largest_video.add_tag(session, tag_name)

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
    __table_args__ = (
        Index('channel_minimum_frequency_idx', 'minimum_frequency'),
        Index('channel_source_id', 'source_id'),
        Index('channel_total_size_idx', 'total_size'),
        Index('channel_video_count_idx', 'video_count'),
        Index('channel_url_key', 'url', unique=True, postgresql_where=text('url IS NOT NULL')),
    )
    id = Column(Integer, primary_key=True)
    # name and directory are stored in Collection, accessed via properties
    url = Column(String)  # will only be downloaded if related Download exists. Partial unique index on non-NULL values.
    generate_posters = Column(Boolean, default=False)  # generating posters may delete files, and can be slow.
    calculate_duration = Column(Boolean, default=True)  # use ffmpeg to extract duration (slower than info json).
    download_missing_data = Column(Boolean, default=True)  # fetch missing data like `source_id` and video comments.
    source_id = Column(String)  # the ID from the source website.
    refreshed = Column(Boolean, default=False)  # The files in the Channel have been refreshed.

    # Columns updated by triggers
    video_count = Column(Integer, default=0, nullable=False)  # update_channel_video_count
    total_size = Column(BigInteger, default=0, nullable=False)  # update_channel_size
    minimum_frequency = Column(Integer)  # update_channel_minimum_frequency

    info_json = deferred(Column(JSONB))
    info_date = Column(Date)

    videos: InstrumentedList = relationship('Video', primaryjoin='Channel.id==Video.channel_id')
    collection_id = Column(Integer, ForeignKey('collection.id', ondelete='CASCADE'))
    collection = relationship('Collection', foreign_keys=[collection_id])

    @property
    def downloads(self) -> InstrumentedList:
        """Get downloads from associated Collection."""
        return self.collection.downloads if self.collection else []

    def __repr__(self):
        return f'<Channel id={self.id} name={repr(self.name)} url={self.url} directory={self.directory}>'

    @property
    def name(self) -> str | None:
        """Delegate name to Collection"""
        return self.collection.name if self.collection else None

    @name.setter
    def name(self, value: str):
        """Set name on Collection"""
        if self.collection:
            self.collection.name = value

    @property
    def directory(self) -> pathlib.Path | None:
        """Delegate directory to Collection"""
        return self.collection.directory if self.collection else None

    @directory.setter
    def directory(self, value: pathlib.Path | str):
        """Set directory on Collection"""
        if self.collection:
            self.collection.directory = value

    @property
    def tag(self):
        """Delegate tag to Collection"""
        return self.collection.tag if self.collection else None

    @tag.setter
    def tag(self, value):
        """Set tag on Collection"""
        if self.collection:
            self.collection.tag = value

    @property
    def tag_id(self) -> int | None:
        """Delegate tag_id to Collection"""
        return self.collection.tag_id if self.collection else None

    @tag_id.setter
    def tag_id(self, value: int):
        """Set tag_id on Collection"""
        if self.collection:
            self.collection.tag_id = value

    @property
    def tag_name(self) -> str | None:
        """Delegate tag_name to Collection"""
        return self.collection.tag_name if self.collection else None

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
        """Delete all Video records (but not video files) related to this Channel.  Then delete the Channel and its Collection."""
        session = Session.object_session(self)

        # Disown the videos.
        videos = session.query(Video).filter_by(channel_id=self.id)
        for video in videos:
            video.channel = None

        for download in self.downloads:
            download: Download
            download.delete()

        # Get the Collection before deleting the Channel
        collection = self.collection

        # Delete the Channel
        session.delete(self)

        # Delete the Collection after Channel to avoid FK constraint issues
        if collection:
            session.delete(collection)

    def update(self, data: dict):
        """
        Update the attributes of this Channel.  Will also update the Channel's Download, if it has one.
        """
        channel_id = self.id
        data = data.copy()

        # URL should not be empty string.
        url = data.pop('url', None)
        self.url = url or None

        session: Session = Session.object_session(self)

        downloads = data.pop('downloads', [])

        if tag_name := data.pop('tag_name', None):
            self.tag = Tag.find_by_name(session, tag_name)

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
                if existing_download := Download.get_by_url(session, url):
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

            download = self.get_or_create_download(session, url, frequency, reset_attempts=True)
            download.collection_id = self.collection_id
            session.add(download)

    def batch_update(self, data: dict, tags_by_name: dict = None, existing_downloads: dict = None):
        """
        Update the attributes of this Channel using pre-fetched lookup dictionaries.
        More efficient than update() when processing many channels because it avoids
        individual database queries for tags and downloads.

        Args:
            data: Config data dict with channel fields
            tags_by_name: Pre-fetched {tag_name: Tag} lookup dictionary
            existing_downloads: Pre-fetched {url: Download} lookup dictionary
        """
        data = data.copy()
        tags_by_name = tags_by_name or {}
        existing_downloads = existing_downloads or {}

        # URL should not be empty string.
        url = data.pop('url', None)
        self.url = url or None

        session: Session = Session.object_session(self)
        downloads = data.pop('downloads', [])

        # Use pre-fetched tag lookup instead of querying
        if tag_name := data.pop('tag_name', None):
            tag = tags_by_name.get(tag_name)
            if tag:
                self.tag = tag
            else:
                logger.warning(f'Tag {repr(tag_name)} not found for channel')

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
                # Use pre-fetched download lookup instead of querying
                if existing_download := existing_downloads.get(url):
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

            download_obj = self.get_or_create_download(session, url, frequency, reset_attempts=True)
            download_obj.collection_id = self.collection_id
            session.add(download_obj)

    def config_view(self) -> dict:
        """
        Retrieve the data about this Channel that should be stored in a config file.
        """
        # Store relative path for portability across different media directories
        try:
            directory = str(get_relative_to_media_directory(self.directory))
        except ValueError:
            # Directory outside media directory, store as-is
            directory = str(self.directory)

        config = dict(
            calculate_duration=self.calculate_duration,
            directory=directory,
            download_missing_data=self.download_missing_data,
            downloads=[{'url': i.url, 'frequency': i.frequency} for i in self.downloads],
            generate_posters=self.generate_posters,
            name=self.name,
            source_id=self.source_id,
            tag_name=self.tag_name,
            url=self.url or None,
        )
        # Include file_format from the underlying Collection
        if self.collection and self.collection.file_format:
            config['file_format'] = self.collection.file_format
        return config

    @classmethod
    def from_config(cls, session: Session, data: dict) -> 'Channel':
        """
        Create or update a Channel from config data. This also creates/updates the Collection.

        Args:
            session: Database session
            data: Config dict containing channel metadata (name, directory, url, source_id, etc.)

        Returns:
            The created or updated Channel
        """
        from wrolpi.collections import Collection

        # Ensure this is treated as a channel collection
        data = data.copy()
        data['kind'] = 'channel'

        # Create or update the Collection first
        collection = Collection.from_config(session, data)

        # Extract Channel-specific fields
        url = data.get('url')
        source_id = data.get('source_id')

        # Find existing Channel by collection_id or create new one
        channel = session.query(cls).filter_by(collection_id=collection.id).one_or_none()

        if not channel:
            # Create new Channel
            channel = cls(
                collection_id=collection.id,
                url=url,
                source_id=source_id,
            )
            session.add(channel)
            session.flush([channel])

        # Use the update() method to handle all fields including downloads
        channel.update(data)

        return channel

    @staticmethod
    def get_by_path(session: Session, path: pathlib.Path) -> Optional['Channel']:
        """
        Find a Channel whose directory contains the given path.

        This method walks up the directory tree from the given path to find
        a Channel whose directory matches. This allows finding channels for
        files in subdirectories (e.g., year subdirectories like 2026/).

        Args:
            session: Database session
            path: Path to search for (can be a file or directory path)

        Returns:
            Channel if found, None otherwise
        """
        if not path:
            raise RuntimeError('Must provide path to get Channel')
        path = pathlib.Path(path) if isinstance(path, str) else path
        if not path.is_absolute():
            path = get_media_directory() / path
        path = path.absolute()

        from wrolpi.collections import Collection
        media_dir = get_media_directory()

        # Walk up the directory tree to find a matching channel
        current = path
        while current != media_dir and current != current.parent:
            channel = session.query(Channel).join(Collection).filter(
                Collection.directory == str(current)
            ).one_or_none()
            if channel:
                return channel
            current = current.parent

        return None

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
        # Add Collection-delegated properties
        d['name'] = self.name
        d['tag_name'] = self.tag_name
        d['rss_url'] = self.get_rss_url()
        d['directory'] = \
            self.directory.relative_to(get_media_directory()) if self.directory else None
        d['needs_reorganization'] = self.collection.needs_reorganization if self.collection else False
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
            self.tag = Tag.find_by_id(session, tag_id_or_name)
        elif isinstance(tag_id_or_name, str):
            self.tag = Tag.find_by_name(session, tag_id_or_name)
        # Copy the id in case some code needs the id before flush.
        self.tag_id = self.tag.id if self.tag else None
        return self.tag

    @classmethod
    def refresh_files(cls, id_: int, send_events: bool = True):
        """Refresh all files within this Channel's directory.  Mark this channel as refreshed."""
        # Get this Channel's info for later.  Refresh may take a long time.
        with get_db_session() as session:
            directory = cls.find_by_id(session, id_).directory

        # Perform info_json in background task.  Channel will be marked as refreshed after this completes.
        async def _():
            # Refresh all files within this channel's directory first.
            job_id = file_worker.queue_refresh([directory])
            await file_worker.wait_for_job(job_id)
            # Update view count second.
            from modules.videos.common import update_view_counts_and_censored
            await update_view_counts_and_censored(id_)
            with get_db_session(commit=True) as session_:
                channel_ = cls.find_by_id(session_, id_)
                channel_.refreshed = True

        background_task(_())

    @staticmethod
    def get_by_id(session: Session, id_: int) -> Optional['Channel']:
        """Attempt to find a Channel with the provided id.  Returns None if it cannot be found."""
        channel = session.query(Channel).filter_by(id=id_).one_or_none()
        return channel

    @staticmethod
    def find_by_id(session: Session, id_: int) -> 'Channel':
        """Find a Channel with the provided id, raises an exception when no Channel is found.

        @raise UnknownChannel: if the channel can not be found"""
        if channel := Channel.get_by_id(session, id_):
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

    def get_or_create_download(self, session: Session, url: str, frequency: int,
                               reset_attempts: bool = False) -> Download:
        """Get a Download record, if it does not exist, create it.  Create a Download if necessary
        which goes into this Channel's directory.

        Delegates to Collection.get_or_create_download() with Channel-specific downloaders.
        """
        from modules.videos.downloader import ChannelDownloader, VideoDownloader

        return self.collection.get_or_create_download(
            session, url, frequency,
            reset_attempts=reset_attempts,
            downloader_name=ChannelDownloader.name,
            sub_downloader_name=VideoDownloader.name
        )

    def get_rss_url(self) -> str | None:
        """Return the RSS Feed URL for this Channel, if any is possible."""
        yt_url = 'youtube.com' in self.url if self.url else False
        yt_source_id = self.source_id.startswith('UC') if self.source_id else False
        if yt_url and yt_source_id:
            return f'https://www.youtube.com/feeds/videos.xml?channel_id={self.source_id}'

    @staticmethod
    def get_by_url(session: Session, url: str) -> Optional['Channel']:
        if not url:
            raise RuntimeError('Must provide URL to get Channel')
        channel = session.query(Channel).filter_by(url=url).one_or_none()
        return channel

    def format_directory(self, tag_name: str) -> pathlib.Path:
        from modules.videos.lib import format_videos_destination
        return format_videos_destination(self.name, tag_name, self.url)

    async def move_channel(self, directory: pathlib.Path, session: Session, send_events: bool = False):
        """Move the files of this Channel into a new directory.

        Delegates to Collection.move_collection which handles file moving and download destinations.
        This method adds Channel-specific config saves.
        """
        if not directory.is_dir():
            raise FileNotFoundError(f'Destination directory does not exist: {directory}')

        # Save channel config before move (Collection handles downloads and tags config)
        from modules.videos.lib import save_channels_config
        save_channels_config.activate_switch()

        # Delegate to Collection.move_collection which handles file moving and download destinations
        await self.collection.move_collection(directory, session, send_events=send_events)

    @staticmethod
    def get_by_source_id(session: Session, source_id: str) -> Optional['Channel']:
        return session.query(Channel).filter_by(source_id=source_id).one_or_none()
