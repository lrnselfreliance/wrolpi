import json
from http import HTTPStatus

import pytest
import yaml

from wrolpi import tags
from wrolpi.errors import FileGroupIsTagged, InvalidTag, UnknownTag, FileGroupAlreadyTagged
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile, Tag


@pytest.mark.asyncio
async def test_tags_file_group_json(test_async_client, test_session, make_files_structure, tag_factory, example_pdf):
    """The tags of a file are returned in its JSON."""
    tag_one = tag_factory()
    tag_two = tag_factory()
    await files_lib.refresh_files()
    file_group: FileGroup = test_session.query(FileGroup).one()

    Tag.tag_file_group(file_group.id, tag_one.id)
    assert file_group.__json__()['tags'] == ['one']

    file_group.add_tag(tag_two.id)
    assert file_group.__json__()['tags'] == ['one', 'two']

    with pytest.raises(FileGroupAlreadyTagged):
        # Cannot tag a FileGroup with the same Tag twice.
        file_group.add_tag(tag_two.id)

    file_group.untag(tag_one.id)
    assert file_group.__json__()['tags'] == ['two']


@pytest.mark.asyncio
async def test_tags_model(test_async_client, test_session, make_files_structure, tag_factory, example_pdf):
    """Can get Tag using class methods."""
    tag1 = tag_factory()
    assert tag1.__json__()

    assert Tag.find_by_id(tag1.id)
    assert Tag.find_by_name(tag1.name)

    assert Tag.get_by_id(123) is None, '.get should return None with bad id'
    assert Tag.get_by_name('bad name') is None, '.get should return None with bad name'

    with pytest.raises(UnknownTag):
        Tag.find_by_id(123)

    with pytest.raises(UnknownTag):
        Tag.find_by_name('bad name')


@pytest.mark.asyncio
async def test_tags_file_group(test_async_client, test_session, make_files_structure, tag_factory, video_bytes,
                               image_bytes_factory):
    """A FileGroup can be tagged with multiple Tags."""
    make_files_structure({
        'video.mp4': video_bytes, 'video.png': image_bytes_factory(),
    })
    await files_lib.refresh_files()
    video_group: FileGroup = test_session.query(FileGroup).one()

    tag_one = tag_factory()
    assert len(tag_one.tag_files) == 0

    Tag.tag_file_group(video_group.id, tag_one.id)
    test_session.commit()
    assert len(tag_one.tag_files) == 1
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['one', ]

    tag_two = tag_factory()
    Tag.tag_file_group(video_group.id, tag_two.id)
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
async def test_tags_config_file(test_async_client, test_session, test_directory, tag_factory, example_pdf, video_file,
                                test_tags_config):
    """Test that the config is updated when a FileGroup is tagged."""
    await files_lib.refresh_files()
    pdf: FileGroup = FileGroup.get_by_path(example_pdf, test_session)
    video: FileGroup = FileGroup.get_by_path(video_file, test_session)
    tag1 = tag_factory()
    tag2 = tag_factory()
    test_session.commit()

    tags.save_tags_config(test_session)
    assert tag1.name in test_tags_config.read_text()
    assert tag2.name in test_tags_config.read_text()

    video.add_tag(tag1.id)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # Tag PDF twice.
    pdf.add_tag(tag1.id)
    pdf.add_tag(tag2.id)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # One TagFile still exists.
    pdf.untag(tag1.id)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # PDF is no longer tagged.
    pdf.untag(tag2.id)
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    video.untag(tag1.id)
    assert str(video_file.relative_to(test_directory)) not in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # No more tags.
    tags_config = tags.get_tags_config()
    assert isinstance(tags_config.tag_files, list) and len(tags_config.tag_files) == 0

    # Removing non-existent tag does not error.
    video.untag(tag1.id)


@pytest.mark.asyncio
async def test_tags_crud(test_async_client, test_session, example_pdf, assert_tags_config):
    """Test API Create/Retrieve/Update/Delete of Tags."""
    pdf = FileGroup.from_paths(test_session, example_pdf)
    test_session.add(pdf)
    test_session.commit()

    # Can get empty tags.
    request, response = await test_async_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == list()

    # Tags can be created.
    content = dict(name='jardín', color='#123456')
    request, response = await test_async_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert_tags_config(tags={'jardín': {'color': '#123456'}})

    # The tag can be retrieved.
    request, response = await test_async_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == [dict(name='jardín', color='#123456', id=1, file_group_count=0, zim_entry_count=0)]

    # Apply the tag to the PDF.
    tag = test_session.query(tags.Tag).one()
    pdf.add_tag(tag.name, test_session)
    test_session.commit()

    # The tag can be updated.
    content = dict(name='ガーデン', color='#000000')
    request, response = await test_async_client.post('/api/tag/1', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    request, response = await test_async_client.get('/api/tag')
    assert response.json['tags'] == [
        dict(name='ガーデン', color='#000000', id=1, file_group_count=1, zim_entry_count=0)]
    assert_tags_config(tags={'ガーデン': {'color': '#000000'}})

    # Conflicting names return an error.
    content = dict(name='ガーデン', color='#111111')
    request, response = await test_async_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_tags_config(tags={'ガーデン': {'color': '#000000'}})

    # Cannot delete Tag that is used.
    request, response = await test_async_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    pdf.untag(tag.id, test_session)
    test_session.commit()

    # Can delete unused Tag.
    request, response = await test_async_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Config is empty.
    assert_tags_config()


@pytest.mark.asyncio
async def test_delete_tagged_file(test_session, example_pdf, tag_factory):
    """You cannot delete a FileGroup if it is tagged."""
    await files_lib.refresh_files()
    tag = tag_factory()

    pdf: FileGroup = test_session.query(FileGroup).one()
    pdf.add_tag(tag.id)
    test_session.commit()

    with pytest.raises(FileGroupIsTagged):
        pdf.delete()

    test_session.commit()
    assert test_session.query(FileGroup).count() == 1


def test_import_empty_tags_config(test_session, test_tags_config):
    """An empty config can be imported."""
    tags.import_tags_config()


@pytest.mark.asyncio
async def test_import_tags_config(test_async_client, test_session, test_directory, test_tags_config,
                                  example_singlefile):
    with test_tags_config.open('wt') as fh:
        data = dict(
            # Tag names can contain Unicode characters.
            tags={'🔫': {'color': '#123456'}},
            tag_files=[
                ('🔫', str(example_singlefile.relative_to(test_directory)), '2000-01-01 01:01:01'),
                ('🔫', 'does not exist', None),
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

    # '🔫' Tag was created.
    assert test_session.query(tags.Tag).count() == 1
    assert test_session.query(tags.Tag).one().name == '🔫'

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.tag_files, 'File was not tagged during import.'


@pytest.mark.asyncio()
async def test_import_tags_config_missing_file(test_session, test_directory, test_tags_config, example_singlefile):
    """A FileGroup should be created (and tagged) when a file exists, but does not yet have a FileGroup."""
    with test_tags_config.open('wt') as fh:
        data = dict(
            # Tag names can contain Unicode characters.
            tags={'🦄': {'color': '#654321'}},
            tag_files=[
                ('🦄', str(example_singlefile.relative_to(test_directory)), '2000-01-01 01:01:01'),
            ],
        )
        yaml.dump(data, fh)

    # Re-initialize config with the data we just saved.
    tags.get_tags_config().initialize()

    tags.import_tags_config(test_session)

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.tag_files, 'File was not tagged during import.'


@pytest.mark.asyncio
async def test_import_tags_delete_missing(test_session, test_directory, test_tags_config, make_files_structure,
                                          tag_factory, test_zim):
    """Tags not in the config are deleted on import.  Tags that are used will not be deleted."""
    from modules.zim import lib as zim_lib

    # Create some tags, use tag1.
    tag1, tag2, tag3, tag4 = tag_factory(), tag_factory(), tag_factory(), tag_factory()
    # use tag1 for FileGroup.
    foo, = make_files_structure({'foo': 'text'})
    foo = FileGroup.from_paths(test_session, foo)
    test_session.flush([foo, ])
    foo.add_tag(tag1.id)
    # use tag4 for Zim entry.
    await zim_lib.add_tag(tag4.name, test_zim.id, 'home')
    tags.save_tags_config()

    # All tags were saved.
    assert tag1.name in test_tags_config.read_text()
    assert tag2.name in test_tags_config.read_text()
    assert tag3.name in test_tags_config.read_text()
    assert tag4.name in test_tags_config.read_text()

    # Delete all tags but tag3.
    config = tags.get_tags_config()
    config_dict = config.dict()
    config_dict['tags'] = {k: v for k, v in config.tags.items() if k == tag3.name}
    config.update(config_dict)
    config.initialize()
    # Tag Files and Tag Zims are untouched.  Only tag3 is left.
    assert len(config.tag_files) == 1
    assert len(config.tag_zims) == 1
    assert len(config.tags) == 1

    # Import the config.  Only unused Tags not in the config are deleted.
    tags.import_tags_config()
    assert {i.name for i in test_session.query(tags.Tag)} == {
        tag1.name,  # tag1 is used by FileGroup.
        # tag2.name,  tag2 is unused, and deleted.
        tag3.name,  # tag3 was not deleted.
        tag4.name,  # tag4 is used by ZimEntry.
    }

    # DB is written to config with only those Tags left.
    tags.save_tags_config()
    # Tags that are used are restored.
    assert len(config.tag_files) == 1
    assert len(config.tag_zims) == 1
    assert len(config.tags) == 3


@pytest.mark.asyncio
async def test_invalid_tag(test_async_client, test_session, test_directory):
    with pytest.raises(InvalidTag):
        tags.upsert_tag('cannot use comma: ,', '#fff')

    with pytest.raises(InvalidTag):
        tags.upsert_tag('invalid color', 'foo')

    with pytest.raises(UnknownTag):
        tags.upsert_tag('Tag ID does not exist', '#fff', 1)

    with pytest.raises(UnknownTag):
        tags.delete_tag(1)
