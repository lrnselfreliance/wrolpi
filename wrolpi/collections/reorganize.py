"""
Collection file reorganization module.

Provides functionality to reorganize files within a Collection to match a new file format.
For example, migrating from flat structure to year-based subdirectories.
"""
import pathlib
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from wrolpi.common import logger, get_media_directory
from wrolpi.files.models import FileGroup

logger = logger.getChild(__name__)

__all__ = ['build_reorganization_plan', 'execute_reorganization', 'format_video_filename']


async def build_reorganization_plan(
        session: Session,
        collection: 'Collection',
        new_format: str,
) -> Dict:
    """
    Build a plan for reorganizing files in a collection to match a new file format.

    This function analyzes all FileGroups in the collection's directory and determines
    what moves are needed to match the new format. Files already at the correct path
    are skipped.

    Args:
        session: Database session
        collection: The Collection to reorganize
        new_format: The new file format template to apply

    Returns:
        Dict with:
            - total_files: Total FileGroups in collection
            - files_to_move: Number of files that need to be moved
            - files_unchanged: Number of files already at correct path
            - moves: List of {from: old_path, to: new_path} dicts
    """
    from modules.archive.lib import format_archive_filename
    from modules.archive.models import Archive
    from sqlalchemy import or_

    if not collection.directory:
        return {
            'total_files': 0,
            'files_to_move': 0,
            'files_unchanged': 0,
            'moves': [],
        }

    # Query all FileGroups in collection's directory (recursive)
    directory_str = str(collection.directory)
    file_groups = session.query(FileGroup).filter(
        or_(
            FileGroup.directory == directory_str,
            FileGroup.directory.like(f'{directory_str}/%')
        )
    ).all()

    moves = []
    files_unchanged = 0

    for fg in file_groups:
        # Get the model (Archive or Video) associated with this FileGroup
        if collection.kind == 'domain':
            archive = session.query(Archive).filter_by(file_group_id=fg.id).one_or_none()
            if not archive:
                continue

            # Generate new filename using format_archive_filename with new template
            new_filename = format_archive_filename(
                title=archive.title or fg.title or 'untitled',
                domain=archive.domain,
                download_date=fg.download_datetime,
                template=new_format,
            )
            new_path = collection.directory / new_filename

        elif collection.kind == 'channel':
            # For videos, use format_video_filename
            from modules.videos.models import Video
            video = session.query(Video).filter_by(file_group_id=fg.id).one_or_none()
            if not video:
                continue

            new_filename = format_video_filename(video, new_format)
            new_path = collection.directory / new_filename
        else:
            continue

        # Check if file is already at correct path
        if fg.primary_path == new_path:
            files_unchanged += 1
            continue

        # Check if only the directory differs (file is in subdirectory of target)
        try:
            fg.primary_path.relative_to(new_path.parent)
            if fg.primary_path.name == new_path.name:
                files_unchanged += 1
                continue
        except ValueError:
            pass

        moves.append({
            'from': str(fg.primary_path.relative_to(collection.directory)),
            'to': str(new_path.relative_to(collection.directory)),
            'file_group_id': fg.id,
        })

    return {
        'total_files': len(file_groups),
        'files_to_move': len(moves),
        'files_unchanged': files_unchanged,
        'moves': moves,
    }


async def execute_reorganization(
        session: Session,
        collection: 'Collection',
        plan: Dict,
        new_format: str,
) -> List[str]:
    """
    Execute a reorganization plan by queuing file moves for background processing.

    This function:
    1. Creates necessary subdirectories
    2. Queues moves to FileWorker for background processing
    3. Updates the collection's file_format to the new format
    4. Returns immediately - moves are processed asynchronously

    Args:
        session: Database session
        collection: The Collection being reorganized
        plan: The plan dict from build_reorganization_plan()
        new_format: The new file format (to save to collection.file_format)

    Returns:
        List of job_ids for tracking move progress
    """
    from wrolpi.files.worker import file_worker

    if not plan['moves']:
        # Nothing to move, just update the format
        collection.file_format = new_format
        session.commit()
        return []

    # Group moves by target directory for efficiency
    moves_by_target: Dict[pathlib.Path, List[pathlib.Path]] = {}
    for move in plan['moves']:
        source = collection.directory / move['from']
        target = collection.directory / move['to']
        target_dir = target.parent

        if target_dir not in moves_by_target:
            moves_by_target[target_dir] = []
        moves_by_target[target_dir].append(source)

    # Create target directories and queue moves for background processing
    job_ids = []
    for target_dir, sources in moves_by_target.items():
        target_dir.mkdir(parents=True, exist_ok=True)
        job_id = file_worker.queue_move(sources, target_dir)
        job_ids.append(job_id)

    # Update collection's file_format
    collection.file_format = new_format
    session.commit()

    logger.info(f'Queued reorganization for collection {collection.name}: {len(plan["moves"])} files in {len(job_ids)} jobs')
    return job_ids


def format_video_filename(video: 'Video', template: str) -> str:
    """
    Generate a video filename using template and video's metadata.

    Uses yt-dlp's prepare_filename() with the video's stored info_json metadata.

    Args:
        video: The Video model
        template: The filename template (e.g., '%(upload_year)s/%(title)s.%(ext)s')

    Returns:
        The formatted filename (may include subdirectory path)
    """
    from modules.videos.downloader import prepare_filename, convert_wrolpi_filename_format
    from modules.videos.lib import get_videos_downloader_config
    from yt_dlp import YoutubeDL
    import copy

    # Convert WROLPi-specific variables to yt-dlp syntax
    converted = convert_wrolpi_filename_format(template)

    # Get yt-dlp options and set our template
    config = get_videos_downloader_config()
    options = copy.deepcopy(config.yt_dlp_options)
    options['outtmpl'] = converted

    ydl = YoutubeDL(options)

    # Build entry from video's stored metadata
    info = video.info_json or {}
    entry = dict(
        uploader=info.get('uploader', ''),
        upload_date=info.get('upload_date', ''),
        id=video.source_id or info.get('id', ''),
        title=info.get('title', video.file_group.title or 'untitled'),
        ext=video.video_path.suffix.lstrip('.') if video.video_path else 'mp4',
    )

    return prepare_filename(entry, ydl=ydl).lstrip('/')
