import pytest

from wrolpi.files import lib as files_lib
from wrolpi.files.models import FileGroup
from wrolpi.tags import TagFile, get_tags_config


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
    tags_config = get_tags_config()
    assert isinstance(tags_config.tags, list) and len(tags_config.tags) == 0

    # Removing non-existent tag does not error.
    video.remove_tag(tag1)
