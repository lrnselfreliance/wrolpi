"""Editing a Video's details from the video page.

Edits never touch yt-dlp's own keys: they are written to the `wrolpi` section of the info json
(`custom_title`, `custom_description`), which the modeler prefers when it derives the Video."""
import json

import pytest

from modules.videos.lib import extract_video_info_json
from modules.videos.models import Video
from modules.videos.video.lib import update_video
from wrolpi.errors import ValidationError


def test_update_video_title(test_session, test_directory, video_factory):
    """The new title lands in the wrolpi section; yt-dlp's title/fulltitle stay as they were.  The
    Video is re-validated, so its title and search text change."""
    video = video_factory(with_info_json={'title': 'Old Title', 'fulltitle': 'Old Title', 'duration': 7,
                                          'formats': ['kept, not cleaned']})
    test_session.commit()
    assert video.file_group.title == 'Old Title'

    update_video(video.file_group_id, '  New Title  ')

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.file_group.title == 'New Title'
    assert video.file_group.a_text == 'New Title'
    assert video.file_group.length == 7, 'Other details from the info json are unchanged'
    info_json = json.loads(video.info_json_path.read_text())
    assert info_json['title'] == 'Old Title' and info_json['fulltitle'] == 'Old Title', 'The original is kept'
    assert info_json['wrolpi']['custom_title'] == 'New Title'
    assert info_json['formats'] == ['kept, not cleaned']


def test_update_video_title_creates_info_json(test_session, test_directory, video_factory):
    """A Video without an info json gets one holding only the wrolpi section."""
    video = video_factory()
    test_session.commit()
    assert video.info_json_path is None

    update_video(video.file_group_id, 'Brand New')

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.file_group.title == 'Brand New'
    assert video.info_json_path and video.info_json_path.is_file()
    info_json = json.loads(video.info_json_path.read_text())
    assert info_json == {'wrolpi': {'custom_title': 'Brand New'}}
    assert video.info_json_path.name in [i['path'] for i in video.file_group.files], 'The new file is tracked'


def test_update_video_description(test_session, test_directory, video_factory):
    """The description lands in the wrolpi section and is indexed; yt-dlp's description stays.
    An empty custom description clears the shown description."""
    video = video_factory(with_info_json={'title': 'Kept', 'description': 'old words'})
    test_session.commit()
    assert video.file_group.c_text == 'old words'

    update_video(video.file_group_id, description='new words\nsecond line')

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.file_group.title == 'Kept'
    assert video.file_group.c_text == 'new words\nsecond line'
    assert video.get_description() == 'new words\nsecond line'
    info_json = json.loads(video.info_json_path.read_text())
    assert info_json['description'] == 'old words', 'The original is kept'
    assert info_json['wrolpi']['custom_description'] == 'new words\nsecond line'

    update_video(video.file_group_id, description='')
    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.get_description() is None
    assert json.loads(video.info_json_path.read_text())['description'] == 'old words'
    assert video.file_group.title == 'Kept'


def test_update_video_nothing(test_session, video_factory):
    video = video_factory(with_info_json={'title': 'Old'})
    test_session.commit()
    with pytest.raises(ValidationError):
        update_video(video.file_group_id)


def test_update_video_title_empty(test_session, video_factory):
    video = video_factory(with_info_json={'title': 'Old'})
    test_session.commit()
    with pytest.raises(ValidationError):
        update_video(video.file_group_id, '   ')
    test_session.expire_all()
    assert Video.find_by_file_group_id(test_session, video.file_group_id).file_group.title == 'Old'


def test_extract_video_info_json_prefers_custom_title(test_session, video_factory):
    """The modeler's reader prefers the wrolpi custom title over fulltitle/title."""
    video = video_factory(with_info_json={'title': 'Orig', 'fulltitle': 'Orig Full',
                                          'wrolpi': {'custom_title': 'Mine &amp; yours'}})
    assert extract_video_info_json(video).title == 'Mine & yours', 'HTML entities are unescaped as for any title'
    video2 = video_factory(with_info_json={'title': 'Orig', 'fulltitle': 'Orig Full', 'wrolpi': {}})
    assert extract_video_info_json(video2).title == 'Orig Full'


@pytest.mark.asyncio
async def test_custom_title_survives_refresh(test_session, test_directory, async_client, video_factory):
    """A file refresh re-models the Video from its files; the custom title must win again."""
    from wrolpi.files.worker import file_worker

    video = video_factory(with_info_json={'title': 'Original'})
    test_session.commit()
    update_video(video.file_group_id, title='Custom', description='custom words')
    video_path = video.video_path
    file_group_id = video.file_group_id

    # Force a full re-model, as a refresh of a modified file does.
    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, file_group_id)
    video.file_group.indexed = False
    video.file_group.title = None
    video.file_group.c_text = None
    test_session.commit()

    job_id = file_worker.queue_refresh([video_path], send_events=False)
    await file_worker.wait_for_job(job_id)

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, file_group_id)
    assert video.file_group.title == 'Custom'
    assert video.get_description() == 'custom words'
    assert json.loads(video.info_json_path.read_text())['title'] == 'Original'


@pytest.mark.asyncio
async def test_video_update_api(async_client, test_session, video_factory, wrol_mode_fixture):
    video = video_factory(with_info_json={'title': 'Old'})
    test_session.commit()

    request, response = await async_client.put(f'/api/videos/{video.file_group_id}',
                                               content=json.dumps({'title': 'Edited'}))
    assert response.status == 200, response.json
    assert response.json['file_group']['title'] == 'Edited'
    assert response.json['file_group']['id'] == video.file_group_id

    request, response = await async_client.put(f'/api/videos/{video.file_group_id}', content=json.dumps({'title': ''}))
    assert response.status == 400

    request, response = await async_client.put(f'/api/videos/{video.file_group_id}', content=json.dumps({}))
    assert response.status == 400

    request, response = await async_client.put(f'/api/videos/{video.file_group_id}',
                                               content=json.dumps({'description': 'about it'}))
    assert response.status == 200, response.json
    assert response.json['file_group']['title'] == 'Edited', 'Title untouched'
    request, response = await async_client.get(f'/api/videos/{video.file_group_id}/description')
    assert response.json['description'] == 'about it'

    request, response = await async_client.put('/api/videos/999999', content=json.dumps({'title': 'x'}))
    assert response.status == 404

    await wrol_mode_fixture(True)
    request, response = await async_client.put(f'/api/videos/{video.file_group_id}',
                                               content=json.dumps({'title': 'Nope'}))
    assert response.status == 403
    await wrol_mode_fixture(False)


@pytest.mark.asyncio
async def test_update_video_wrol_mode(test_session, video_factory, wrol_mode_fixture):
    """The library function refuses in WROL Mode, not only the API route, so no caller can edit."""
    from wrolpi.errors import WROLModeEnabled
    video = video_factory(with_info_json={'title': 'Old'})
    test_session.commit()

    await wrol_mode_fixture(True)
    try:
        with pytest.raises(WROLModeEnabled):
            update_video(video.file_group_id, title='Nope')
    finally:
        await wrol_mode_fixture(False)

    test_session.expire_all()
    assert Video.find_by_file_group_id(test_session, video.file_group_id).file_group.title == 'Old'


@pytest.mark.asyncio
async def test_edit_creates_info_json_that_survives_refresh(test_session, test_directory, async_client,
                                                            video_factory):
    """A Video with no info json is edited (the edit creates one), then its file is refreshed: the
    new sidecar must stay in the FileGroup and the custom title/description must still win."""
    from wrolpi.files.worker import file_worker

    video = video_factory()
    test_session.commit()
    video_path = video.video_path
    file_group_id = video.file_group_id

    update_video(file_group_id, title='Custom', description='my words')
    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, file_group_id)
    assert video.info_json_path and video.info_json_path.is_file()
    assert video.get_description() == 'my words'

    job_id = file_worker.queue_refresh([video_path], send_events=False)
    await file_worker.wait_for_job(job_id)

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, file_group_id)
    assert video.info_json_path is not None, 'The refresh forgot the info json'
    names = {i['path'] for i in video.file_group.files}
    assert video_path.name in names and video.info_json_path.name in names, names
    assert video.file_group.title == 'Custom'
    assert video.get_description() == 'my words'
