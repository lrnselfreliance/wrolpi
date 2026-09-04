import pathlib
import shutil
from typing import List, Optional, Tuple

from wrolpi.captions import FFMPEG_BIN
from wrolpi.cmd import run_command
from wrolpi.common import logger
from wrolpi.vars import DEFAULT_FILE_PERMISSIONS

logger = logger.getChild(__name__)

# ffprobe `codec_name` values that satisfy each user-selectable codec preference.
FFPROBE_VIDEO_CODEC_NAMES = {
    'h264': {'h264'},
    'hevc': {'hevc', 'h265'},
    'vp9': {'vp9'},
    'av1': {'av1'},
    'vp8': {'vp8'},
}
FFPROBE_AUDIO_CODEC_NAMES = {
    'aac': {'aac'},
    'opus': {'opus'},
    'mp3': {'mp3'},
    'vorbis': {'vorbis'},
}

# Codecs which can be a transcode *target*, mapped to their ffmpeg encoder args.  Encoding VP9/AV1
# in software is impractically slow on a Raspberry Pi, so only widely-playable targets are offered;
# these maps are the extension point for adding more targets later.
TRANSCODE_VIDEO_TARGETS = {
    'h264': ('-c:v', 'libx264', '-preset', 'medium', '-crf', '23'),
}
TRANSCODE_AUDIO_TARGETS = {
    'aac': ('-c:a', 'aac', '-b:a', '192k'),
    'opus': ('-c:a', 'libopus', '-b:a', '128k'),
    'mp3': ('-c:a', 'libmp3lame', '-q:a', '2'),
}

# Containers that can hold an h264/aac transcode result.  webm cannot.
TRANSCODE_CONTAINERS = ('mp4', 'mkv')

TRANSCODE_TIMEOUT = 4 * 60 * 60  # A long video on a Raspberry Pi can take hours.

# Transcoding writes a whole new copy of the video next to the original.
MINIMUM_FREE_SPACE_RATIO = 1.5


def get_stream_codec_names(ffprobe_data: dict, codec_type: str) -> List[str]:
    """Return the codec_name of every stream of the given type ('video' or 'audio').

    Embedded thumbnails appear as mjpeg/png video streams; they are not real video."""
    streams = (ffprobe_data or {}).get('streams') or []
    names = [s.get('codec_name') for s in streams if s.get('codec_type') == codec_type]
    if codec_type == 'video':
        names = [i for i in names if i not in ('mjpeg', 'png')]
    return [i for i in names if i]


def codecs_match(ffprobe_data: dict, video_codecs: List[str], audio_codecs: List[str]) \
        -> Tuple[bool, bool]:
    """Return (video matches, audio matches) for the codec preferences.

    An empty preference list always matches.  A missing stream also matches (an audio-only file
    has no video stream to enforce)."""
    video_match = True
    if video_codecs:
        names = get_stream_codec_names(ffprobe_data, 'video')
        if names:
            acceptable = set().union(*(FFPROBE_VIDEO_CODEC_NAMES.get(i, {i}) for i in video_codecs))
            video_match = any(i in acceptable for i in names)
    audio_match = True
    if audio_codecs:
        names = get_stream_codec_names(ffprobe_data, 'audio')
        if names:
            acceptable = set().union(*(FFPROBE_AUDIO_CODEC_NAMES.get(i, {i}) for i in audio_codecs))
            audio_match = any(i in acceptable for i in names)
    return video_match, audio_match


def get_transcode_target(preferences: List[str], targets: dict) -> Optional[str]:
    """The first preferred codec that is a supported transcode target, or None."""
    for codec in preferences or []:
        if codec in targets:
            return codec
    return None


async def transcode_video_file(video_path: pathlib.Path,
                               target_vcodec: Optional[str] = None,
                               target_acodec: Optional[str] = None,
                               container: str = 'mp4') -> pathlib.Path:
    """Transcode a video file in place (same stem, possibly a new container extension).

    Only the stream(s) with a target are re-encoded; the other stream is copied.  The output is
    written to a temporary file in the same directory, then atomically renamed over the final
    path.  The original file is deleted if the extension changed.  Returns the final path.

    @raise RuntimeError: when ffmpeg fails, or there is not enough free disk space.
    """
    if not FFMPEG_BIN:
        raise RuntimeError('ffmpeg was not found')
    if not target_vcodec and not target_acodec:
        raise RuntimeError('Refusing to transcode without a target codec')
    if container not in TRANSCODE_CONTAINERS:
        logger.info(f'Forcing mp4 container for transcode of {video_path} ({container} is not supported)')
        container = 'mp4'

    source_size = video_path.stat().st_size
    free = shutil.disk_usage(video_path.parent).free
    if free < MINIMUM_FREE_SPACE_RATIO * source_size:
        raise RuntimeError(
            f'Not enough free space to transcode {video_path} ({free} bytes free, source is {source_size} bytes)')

    video_args = TRANSCODE_VIDEO_TARGETS[target_vcodec] if target_vcodec else ('-c:v', 'copy')
    audio_args = TRANSCODE_AUDIO_TARGETS[target_acodec] if target_acodec else ('-c:a', 'copy')

    final_path = video_path.with_suffix(f'.{container}')
    tmp_path = video_path.with_suffix(f'.transcode.{container}')
    cmd = (FFMPEG_BIN, '-y',
           '-i', video_path,
           '-map', '0:v:0', '-map', '0:a:0',
           *video_args,
           *audio_args,
           '-movflags', '+faststart',
           str(tmp_path))
    logger.warning(f'Transcoding {video_path} to {final_path} (video={target_vcodec}, audio={target_acodec})')
    try:
        result = await run_command(cmd, cwd=video_path.parent, timeout=TRANSCODE_TIMEOUT)
        if result.return_code != 0:
            raise RuntimeError(
                f'ffmpeg exited with {result.return_code} while transcoding {video_path}:'
                f'\n{result.stderr.decode()[-2000:]}')
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    # The old ffprobe sidecar describes the old streams.
    video_path.with_suffix('.ffprobe.json').unlink(missing_ok=True)
    tmp_path.rename(final_path)
    if final_path != video_path:
        video_path.unlink()
    final_path.chmod(DEFAULT_FILE_PERMISSIONS)
    return final_path
