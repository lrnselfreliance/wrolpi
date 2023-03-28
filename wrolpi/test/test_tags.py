import json
from http import HTTPStatus

import pytest

from wrolpi import tags
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile


@pytest.mark.asyncio
async def test_tags_file_group_json(test_session, make_files_structure, tag_factory, example_pdf):
    """The tags of a file are returned in it's JSON."""
    tag_one = tag_factory()
    tag_two = tag_factory()
    await files_lib.refresh_files()
    file_group: FileGroup = test_session.query(FileGroup).one()

    tag_one.add_tag(file_group)
    assert file_group.__json__()['tags'] == ['one']

    file_group.add_tag(tag_two)
    assert file_group.__json__()['tags'] == ['one', 'two']

    file_group.remove_tag(tag_one)
    assert file_group.__json__()['tags'] == ['two']


@pytest.mark.asyncio
async def test_tags_file_group(test_session, make_files_structure, tag_factory):
    """A FileGroup can be tagged with multiple Tags."""
    make_files_structure(['video.mp4', 'video.png'])
    await files_lib.refresh_files()
    video_group: FileGroup = test_session.query(FileGroup).one()

    tag_one = tag_factory()
    assert len(tag_one.tag_files) == 0

    tag_one.add_tag(video_group)
    test_session.commit()
    assert len(tag_one.tag_files) == 1
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['one', ]

    tag_two = tag_factory()
    tag_two.add_tag(video_group)
    test_session.commit()
    assert len(tag_one.tag_files) == 1
    assert len(tag_two.tag_files) == 1

    # Video has both tags.
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['one', 'two']
    assert test_session.query(TagFile).count() == 2

    # Deleting the tag deletes the tag_file.
    test_session.delete(tag_one)
    test_session.commit()
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['two', ]
    assert test_session.query(TagFile).count() == 1


@pytest.mark.asyncio
async def test_tags_config_(test_session, test_directory, tag_factory, example_pdf, video_file, test_tags_config):
    """Test that the config is updated when a FileGroup is tagged."""
    await files_lib.refresh_files()
    pdf: FileGroup = FileGroup.find_by_path(example_pdf, test_session)
    video: FileGroup = FileGroup.find_by_path(video_file, test_session)
    tag1 = tag_factory()
    tag2 = tag_factory()
    test_session.commit()

    tags.schedule_save(test_session)
    assert tag1.name in test_tags_config.read_text()
    assert tag2.name in test_tags_config.read_text()

    video.add_tag(tag1)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # Tag PDF twice.
    pdf.add_tag(tag1)
    pdf.add_tag(tag2)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # One TagFile still exists.
    pdf.remove_tag(tag1)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # PDF is no longer tagged.
    pdf.remove_tag(tag2)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    video.remove_tag(tag1)
    assert str(video_file.relative_to(test_directory)) not in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # No more tags.
    tags_config = tags.get_tags_config()
    assert isinstance(tags_config.tag_files, list) and len(tags_config.tag_files) == 0

    # Removing non-existent tag does not error.
    video.remove_tag(tag1)


def test_tags_crud(test_session, test_client, example_pdf):
    """Test API Create/Retrieve/Update/Delete of Tags."""
    pdf = FileGroup.from_paths(test_session, example_pdf)
    test_session.add(pdf)
    test_session.commit()

    # Can get empty tags.
    request, response = test_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == list()

    # Tags can be created.
    content = dict(name='foo', color='#123456')
    request, response = test_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED

    # The tag can be retrieved.
    request, response = test_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == [dict(name='foo', color='#123456', id=1)]

    # Apply the tag to the PDF.
    tag = test_session.query(tags.Tag).one()
    pdf.add_tag(tag, test_session)
    test_session.commit()

    # The tag can be updated.
    content = dict(name='bar', color='#000000')
    request, response = test_client.post('/api/tag/1', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    request, response = test_client.get('/api/tag')
    assert response.json['tags'] == [dict(name='bar', color='#000000', id=1)]

    # Conflicting names return an error.
    content = dict(name='bar', color='#111111')
    request, response = test_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    # Cannot delete Tag that is used.
    request, response = test_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    pdf.remove_tag(tag, test_session)
    test_session.commit()

    # Can delete unused Tag.
    request, response = test_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.NO_CONTENT


@pytest.mark.asyncio
async def test_delete_tagged_file(test_session, example_pdf, tag_factory):
    await files_lib.refresh_files()
    tag = tag_factory()

    pdf: FileGroup = test_session.query(FileGroup).one()
    pdf.add_tag(tag)
    test_session.commit()

    pdf.delete()
    test_session.commit()
