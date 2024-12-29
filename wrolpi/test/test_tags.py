import json
from http import HTTPStatus

import pytest
import yaml

from wrolpi import tags
from wrolpi.common import is_hardlinked, walk
from wrolpi.errors import FileGroupIsTagged, InvalidTag, UnknownTag, UsedTag
from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile, Tag


@pytest.mark.asyncio
async def test_tags_file_group_json(async_client, test_session, make_files_structure, tag_factory, example_pdf):
    """The tags of a file are returned in its JSON."""
    tag_one = await tag_factory()
    tag_two = await tag_factory()
    await files_lib.refresh_files()
    file_group: FileGroup = test_session.query(FileGroup).one()

    file_group.add_tag(tag_one.id)
    assert file_group.__json__()['tags'] == ['one']

    file_group.add_tag(tag_two.name)
    assert file_group.__json__()['tags'] == ['one', 'two']

    file_group.untag(tag_one.id)
    assert file_group.__json__()['tags'] == ['two']

    file_group.untag(tag_two.name)
    assert file_group.__json__()['tags'] == []


@pytest.mark.asyncio
async def test_tags_model(async_client, test_session, make_files_structure, tag_factory, example_pdf):
    """Can get Tag using class methods."""
    tag1 = await tag_factory()
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
async def test_tags_file_group(async_client, test_session, make_files_structure, tag_factory, video_bytes,
                               image_bytes_factory):
    """A FileGroup can be tagged with multiple Tags."""
    make_files_structure({
        'video.mp4': video_bytes, 'video.png': image_bytes_factory(),
    })
    await files_lib.refresh_files()
    video_group: FileGroup = test_session.query(FileGroup).one()

    tag_one = await tag_factory()
    assert len(tag_one.tag_files) == 0

    video_group.add_tag(tag_one.id)
    test_session.commit()
    assert len(tag_one.tag_files) == 1
    assert sorted([i.tag.name for i in video_group.tag_files]) == ['one', ]

    tag_two = await tag_factory()
    video_group.add_tag(tag_two.id)
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
async def test_tags_config_file(test_session, test_directory, tag_factory, example_pdf, video_file, await_switches,
                                test_tags_config):
    """Test that the config is updated when a FileGroup is tagged."""
    await files_lib.refresh_files()
    pdf: FileGroup = FileGroup.get_by_path(example_pdf, test_session)
    video: FileGroup = FileGroup.get_by_path(video_file, test_session)
    tag1 = await tag_factory()
    tag2 = await tag_factory()
    test_session.commit()
    await await_switches()
    # tags.get_tags_config().successful_import = True

    tags.save_tags_config()
    assert tag1.name in test_tags_config.read_text()
    assert tag2.name in test_tags_config.read_text()

    video.add_tag(tag1.id)
    await await_switches()
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # Tag PDF twice.
    pdf.add_tag(tag1.id)
    pdf.add_tag(tag2.id)
    await await_switches()
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # One TagFile still exists.
    pdf.untag(tag1.id)
    await await_switches()
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) in test_tags_config.read_text()

    # PDF is no longer tagged.
    pdf.untag(tag2.id)
    await await_switches()
    assert str(video_file.relative_to(test_directory)) in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    video.untag(tag1.id)
    await await_switches()
    assert str(video_file.relative_to(test_directory)) not in test_tags_config.read_text()
    assert str(example_pdf.relative_to(test_directory)) not in test_tags_config.read_text()

    # No more tags.
    tags_config = tags.get_tags_config()
    assert isinstance(tags_config.tag_files, list) and len(tags_config.tag_files) == 0

    # Removing non-existent tag does not error.
    video.untag(tag1.id)


@pytest.mark.asyncio
async def test_tags_crud(async_client, test_session, example_pdf, assert_tags_config):
    """Test API Create/Retrieve/Update/Delete of Tags."""
    pdf = FileGroup.from_paths(test_session, example_pdf)
    test_session.add(pdf)
    test_session.commit()

    # Can get empty tags.
    request, response = await async_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == list()

    # Tags can be created.
    content = dict(name='jardín', color='#123456')
    request, response = await async_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.CREATED
    assert_tags_config(tags={'jardín': {'color': '#123456'}})

    # The tag can be retrieved.
    request, response = await async_client.get('/api/tag')
    assert response.status_code == HTTPStatus.OK
    assert response.json['tags'] == [dict(name='jardín', color='#123456', id=1, file_group_count=0, zim_entry_count=0)]

    # Apply the tag to the PDF.
    tag = test_session.query(tags.Tag).one()
    pdf.add_tag(tag.name, test_session)
    test_session.commit()

    # The tag can be updated.
    content = dict(name='ガーデン', color='#000000')
    request, response = await async_client.post('/api/tag/1', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    request, response = await async_client.get('/api/tag')
    assert response.json['tags'] == [
        dict(name='ガーデン', color='#000000', id=1, file_group_count=1, zim_entry_count=0)]
    assert_tags_config(tags={'ガーデン': {'color': '#000000'}})

    # Tag color can be changed
    content = dict(name='ガーデン', color='#ffffff')
    request, response = await async_client.post('/api/tag/1', content=json.dumps(content))
    assert response.status_code == HTTPStatus.OK
    assert Tag.find_by_name('ガーデン').color == '#ffffff'

    # Conflicting names return an error.
    content = dict(name='ガーデン', color='#111111')
    request, response = await async_client.post('/api/tag', content=json.dumps(content))
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert_tags_config(tags={'ガーデン': {'color': '#ffffff'}})

    # Cannot delete Tag that is used.
    request, response = await async_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.BAD_REQUEST

    pdf.untag(tag.id, test_session)
    test_session.commit()

    # Can delete unused Tag.
    request, response = await async_client.delete('/api/tag/1')
    assert response.status_code == HTTPStatus.NO_CONTENT

    # Config is empty.
    assert_tags_config()


@pytest.mark.asyncio
async def test_delete_tagged_file(test_session, example_pdf, tag_factory):
    """You cannot delete a FileGroup if it is tagged."""
    await files_lib.refresh_files()
    tag = await tag_factory()

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
async def test_import_tags_config(async_client, test_session, test_directory, test_tags_config,
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

    tags.import_tags_config()

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

    tags.import_tags_config()

    file_group: FileGroup = test_session.query(FileGroup).one()
    assert file_group.tag_files, 'File was not tagged during import.'


@pytest.mark.asyncio
async def test_import_tags_delete_missing(test_session, test_directory, test_tags_config, make_files_structure,
                                          tag_factory, test_zim, await_switches):
    """Tags not in the config are deleted on import.  Tags that are used will not be deleted."""
    from modules.zim import lib as zim_lib

    # Create some tags, use tag1.
    tag1, tag2, tag3, tag4 = await tag_factory(), await tag_factory(), await tag_factory(), await tag_factory()
    # use tag1 for FileGroup.
    foo, = make_files_structure({'foo': 'text'})
    foo = FileGroup.from_paths(test_session, foo)
    test_session.flush([foo, ])
    foo.add_tag(tag1.id)
    # use tag4 for Zim entry.
    await zim_lib.add_tag(tag4.name, test_zim.id, 'home')
    tags.save_tags_config.activate_switch()
    await await_switches()

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
    await await_switches()
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
    tags.save_tags_config.activate_switch()
    await await_switches()
    # Tags that are used are restored.
    assert len(config.tag_files) == 1
    assert len(config.tag_zims) == 1
    assert len(config.tags) == 3


@pytest.mark.asyncio
async def test_invalid_tag(async_client, test_session, test_directory):
    with pytest.raises(InvalidTag):
        await tags.upsert_tag('cannot use comma: ,', '#fff')

    with pytest.raises(InvalidTag):
        await tags.upsert_tag('invalid color', 'foo')

    with pytest.raises(UnknownTag):
        await tags.upsert_tag('Tag ID does not exist', '#fff', 1)


@pytest.mark.asyncio
async def test_tags_directory(test_session, test_directory, tag_factory, video_factory, example_pdf, await_switches):
    """Test that Tag Directory is synchronized with database."""
    readme = test_directory / 'tags/README.txt'

    # Should be deleted on sync.
    (test_directory / 'tags/should be deleted').mkdir(parents=True)
    (test_directory / 'tags/cannot be deleted').mkdir(parents=True)
    (test_directory / 'tags/cannot be deleted/because of this file').touch()

    tag1, tag2 = await tag_factory('First Aid'), await tag_factory('Special/name')
    vid1 = video_factory(with_video_file=test_directory / 'vid1.mp4', with_caption_file=True, with_info_json=True,
                         with_poster_ext='jpg')
    vid2 = video_factory(with_video_file=test_directory / 'vid2.mp4', with_info_json=True)
    pdf = FileGroup.from_paths(test_session, example_pdf)
    test_session.commit()
    await await_switches()
    assert 'vid1' in str(vid1.file_group.primary_path)
    assert 'vid2' in str(vid2.file_group.primary_path)
    assert 'pdf' in str(pdf.primary_path)
    assert readme.is_file() and readme.stat().st_size > 0

    def assert_tag_links(paths: list[str]):
        for path in paths:
            path = test_directory / f'tags/{path}'
            if not path.is_file():
                raise AssertionError(f'Expected {path} to be a file')
            if not is_hardlinked(path):
                raise AssertionError(f'Expected {path} to be linked')

        # Readme should always exist.
        assert readme.is_file() and readme.stat().st_size > 0

    # Video1 tagged with First Aid and Special/name.
    vid1.add_tag(tag1.id)
    vid1.add_tag(tag2.id)
    # Video2 tagged with First Aid.
    vid2.add_tag(tag1.id)
    # PDF tagged with Special/name.
    pdf.add_tag(tag2.id)
    await await_switches()
    assert_tag_links([
        'First Aid, Special⧸name/vid1.en.vtt',
        'First Aid, Special⧸name/vid1.en.vtt',
        'First Aid, Special⧸name/vid1.info.json',
        'First Aid, Special⧸name/vid1.jpg',
        'First Aid, Special⧸name/vid1.mp4',
        'First Aid/vid2.info.json',
        'First Aid/vid2.mp4',
        'Special⧸name/pdf example.pdf',
    ])

    # Extra directories and files are deleted, if possible.
    assert len(list(walk(test_directory / 'tags'))) == 13
    assert not (test_directory / 'tags/should be deleted').exists()
    assert (test_directory / 'tags/cannot be deleted/because of this file').is_file()
    assert test_session.query(TagFile).count() == 4

    # Video1 tagged with First Aid only.
    vid1.untag(tag2.id)
    await await_switches()
    assert_tag_links([
        'First Aid/vid1.en.vtt',
        'First Aid/vid1.en.vtt',
        'First Aid/vid1.info.json',
        'First Aid/vid1.jpg',
        'First Aid/vid1.mp4',
        'First Aid/vid2.info.json',
        'First Aid/vid2.mp4',
        'Special⧸name/pdf example.pdf',
    ])
    assert len(list(walk(test_directory / 'tags'))) == 12
    assert not (test_directory / 'tags/First Aid, Special⧸name').exists()
    assert test_session.query(TagFile).count() == 3

    # PDF no longer tagged.
    pdf.untag(tag2.id)
    await await_switches()
    assert_tag_links([
        'First Aid/vid1.en.vtt',
        'First Aid/vid1.en.vtt',
        'First Aid/vid1.info.json',
        'First Aid/vid1.jpg',
        'First Aid/vid1.mp4',
        'First Aid/vid2.info.json',
        'First Aid/vid2.mp4',
    ])
    assert len(list(walk(test_directory / 'tags'))) == 10
    assert not (test_directory / 'tags/Special⧸name').exists()
    assert not (test_directory / 'tags/Special⧸name/pdf example.pdf').exists()
    assert test_session.query(TagFile).count() == 2

    # No more tagged files.
    vid1.untag(tag1.id)
    vid2.untag(tag1.id)
    await await_switches()
    assert test_session.query(TagFile).count() == 0
    # Readme, and un-deletable file and directory exist.
    assert len(list(walk(test_directory / 'tags'))) == 3
    assert (test_directory / 'tags').is_dir()
    assert not (test_directory / 'tags/First Aid').exists(), \
        f'First Aid lingers and contains: {[i.name for i in (test_directory / "tags/First Aid").iterdir()]}'

    # Only three FileGroups were created.  Tags Directory files are ignored during refresh.
    await files_lib.refresh_files()
    assert test_session.query(FileGroup).count() == 3


@pytest.mark.asyncio
async def test_update_tag(test_session, test_directory, video_factory, tag_factory, await_switches):
    """Linked files in the Tag Directory are moved when the tag is renamed."""
    # Create tagged Video.
    tag = await tag_factory()
    video_factory(title='video', tag_names=[tag.name])
    test_session.commit()
    await await_switches()

    # Video file is linked in tag directory.
    assert (test_directory / 'tags').is_dir()
    assert (test_directory / 'videos/NO CHANNEL/video.mp4').is_file()
    assert (test_directory / 'tags/one/video.mp4').is_file()

    # Invalid characters are replaced during rename.
    await tags.upsert_tag('new/name%', tag.color, tag.id)
    await await_switches()

    # Video file was moved.
    assert (test_directory / 'tags').is_dir()
    assert (test_directory / 'videos/NO CHANNEL/video.mp4').is_file()
    assert not (test_directory / 'tags/one/video.mp4').exists()
    assert (test_directory / 'tags/new⧸name/video.mp4').is_file()


@pytest.mark.asyncio
async def test_tag_rename_with_channel(test_session, test_directory, video_factory, tag_factory,
                                       channel_factory, await_switches):
    tag = await tag_factory()
    channel = channel_factory(name='Channel Name', tag_name=tag.name)
    video_factory(title='video', channel_id=channel.id)
    test_session.commit()
    await await_switches()

    assert (test_directory / 'tags').is_dir()
    assert (test_directory / 'videos/one/Channel Name').is_dir()
    assert (test_directory / 'videos/one/Channel Name/video.mp4').is_file()

    await tag.update_tag('New Tag Name', None, session=test_session)

    assert (test_directory / 'tags').is_dir()
    assert (test_directory / 'videos/New Tag Name/Channel Name').is_dir()
    assert (test_directory / 'videos/New Tag Name/Channel Name/video.mp4').is_file()

    # Cannot delete Tag when used by Channel.  This prevents the need to move Channel directories when Tags are deleted.
    with pytest.raises(UsedTag):
        tag.delete()
