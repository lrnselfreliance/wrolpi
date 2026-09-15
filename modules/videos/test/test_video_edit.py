"""Editing a Video's details from the video page."""
import json

import pytest

from modules.videos.models import Video
from modules.videos.video.lib import update_video
from wrolpi.errors import ValidationError


def test_update_video_title(test_session, test_directory, video_factory):
    """The new title is written to the info json (title and fulltitle) and the Video re-validated,
    so its title and search text change too.  Other info json keys are kept."""
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
    assert info_json['title'] == 'New Title' and info_json['fulltitle'] == 'New Title'
    assert info_json['formats'] == ['kept, not cleaned']


def test_update_video_title_creates_info_json(test_session, test_directory, video_factory):
    """A Video without an info json gets one holding the title."""
    video = video_factory()
    test_session.commit()
    assert video.info_json_path is None

    update_video(video.file_group_id, 'Brand New')

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.file_group.title == 'Brand New'
    assert video.info_json_path and video.info_json_path.is_file()
    assert json.loads(video.info_json_path.read_text())['title'] == 'Brand New'
    assert video.info_json_path.name in [i['path'] for i in video.file_group.files], 'The new file is tracked'


def test_update_video_description(test_session, test_directory, video_factory):
    """The description is written to the info json and indexed; the title is untouched when not
    given.  An empty description clears it."""
    video = video_factory(with_info_json={'title': 'Kept', 'description': 'old words'})
    test_session.commit()
    assert video.file_group.c_text == 'old words'

    update_video(video.file_group_id, description='new words\nsecond line')

    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.file_group.title == 'Kept'
    assert video.file_group.c_text == 'new words\nsecond line'
    assert video.get_description() == 'new words\nsecond line'
    assert json.loads(video.info_json_path.read_text())['description'] == 'new words\nsecond line'

    update_video(video.file_group_id, description='')
    test_session.expire_all()
    video = Video.find_by_file_group_id(test_session, video.file_group_id)
    assert video.get_description() is None
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
