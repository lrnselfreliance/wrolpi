import json
from http import HTTPStatus

import pytest
import yaml

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

    tag_one.add_file_group_tag(file_group)
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

    tag_one.add_file_group_tag(video_group)
    test_session.commit()
    assert len(tag_one.tag_files) == 1
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['one', ]

    tag_two = tag_factory()
    tag_two.add_file_group_tag(video_group)
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


def test_tags_crud(test_session, test_client, example_pdf, assert_tags_config):
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
    assert_tags_config(tags={'foo': {'color': '#123456'}})

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
    assert_tags_config(tags={'bar': {'color': '#000000'}})

    # Conflicting names return an error.
    content = dict(name='bar', color='#111111')
    request, response = test_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_tags_config(tags={'bar': {'color': '#000000'}})

    # Cannot delete Tag that is used.
    request, response = test_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    pdf.remove_tag(tag, test_session)
    test_session.commit()

    # Can delete unused Tag.
    request, response = test_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Config is empty.
    assert_tags_config()


@pytest.mark.asyncio
async def test_delete_tagged_file(test_session, example_pdf, tag_factory):
    await files_lib.refresh_files()
    tag = tag_factory()

    pdf: FileGroup = test_session.query(FileGroup).one()
    pdf.add_tag(tag)
    test_session.commit()

    pdf.delete()
    test_session.commit()


def test_import_empty_tags_config(test_session, test_tags_config):
    """An empty config can be imported."""
    tags.import_tags_config()


@pytest.mark.asyncio()
async def test_import_tags_config(test_session, test_directory, test_tags_config, example_singlefile):
    with test_tags_config.open('wt') as fh:
        data = dict(
            tags={'Foo': {'color': '#123456'}},
            tag_files=[
                ('Foo', str(example_singlefile.relative_to(test_directory))),
                ('Foo', 'does not exist'),
            ],
        )
        yaml.dump(data, fh)

    assert test_session.query(tags.Tag).count() == 0, 'Expected no Tags.'
    assert test_session.query(tags.TagFile).count() == 0, 'Expected no FileGroups to be tagged.'

    # Re-initialize config with the data we just saved.
    tags.get_tags_config().initialize()

    FileGroup.from_paths(test_session, example_singlefile)
    test_session.commit()

    tags.import_tags_config(test_session)

    # 'Foo' Tag was created.
    assert test_session.query(tags.Tag).count() == 1

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.tag_files, 'File was not tagged during import.'

    # Importing again does not change count.
    await files_lib.refresh_files()
    tags.import_tags_config(test_session)
    assert test_session.query(tags.Tag).count() == 1
    assert test_session.query(tags.TagFile).count() == 1
    # Example file, and the config file.
    assert test_session.query(FileGroup).count() == 2
