"""Tests for the on-disk playlist sync: tag namespacing, safe deletion, and directory cleanup."""
import pytest

from wrolpi.collections.models import Collection
from wrolpi.collections.sync import sync_playlists_directory, get_playlists_directory, \
    validate_playlists_destination
from wrolpi.common import get_wrolpi_config
from wrolpi.tags import Tag


def _make_playlist(session, name, tag=None):
    collection = Collection(name=name, kind='playlist')
    session.add(collection)
    session.flush([collection])
    if tag is not None:
        collection.tag_id = tag.id
        session.flush()
    return collection


def test_untagged_playlist_lives_at_top_level(test_session, test_directory):
    """An untagged playlist syncs to <playlists>/<name>."""
    _make_playlist(test_session, 'Fire Making')
    test_session.commit()

    sync_playlists_directory()

    assert (get_playlists_directory() / 'Fire Making').is_dir()


def test_tagged_playlist_namespaced_under_tag(test_session, test_directory):
    """A tagged playlist syncs to <playlists>/<tag>/<name>."""
    tag = Tag(name='Survival')
    test_session.add(tag)
    test_session.flush()
    _make_playlist(test_session, 'Fire Making', tag=tag)
    test_session.commit()

    sync_playlists_directory()

    assert (get_playlists_directory() / 'Survival' / 'Fire Making').is_dir()
    assert not (get_playlists_directory() / 'Fire Making').exists()


def test_remove_item_deletes_hardlink_keeps_original(test_session, test_directory):
    """Removing a file item deletes its hard link from the playlist dir, but keeps the original."""
    from wrolpi.files.models import FileGroup

    source = test_directory / 'guide.pdf'
    source.write_bytes(b'%PDF-1.4 test')
    file_group = FileGroup.from_paths(test_session, source)
    test_session.commit()

    collection = _make_playlist(test_session, 'Docs')
    item = collection.add_file_group(file_group, session=test_session)
    test_session.commit()

    sync_playlists_directory()
    link = get_playlists_directory() / 'Docs' / '0001_guide.pdf'
    assert link.is_file(), 'hard link should be created'
    assert source.is_file()

    collection.remove_item(test_session, item.id)
    test_session.commit()

    sync_playlists_directory()
    assert not link.exists(), 'hard link should be removed when the item is removed'
    assert source.is_file(), 'the original file must survive'


def test_delete_playlist_removes_its_directory(test_session, test_directory):
    """Deleting a playlist removes its on-disk directory."""
    collection = _make_playlist(test_session, 'Temp')
    collection.add_url(test_session, '/map?lat=1&lon=2&z=3', title='spot')
    test_session.commit()

    sync_playlists_directory()
    directory = get_playlists_directory() / 'Temp'
    assert directory.is_dir()

    # Delete the playlist; the next sync should prune its now-orphaned directory.
    test_session.delete(collection)
    test_session.commit()

    sync_playlists_directory()
    assert not directory.exists()


def test_sync_refuses_to_delete_non_hardlinked_file(test_session, test_directory):
    """A managed-looking file with no other hard link (and not a stub) is preserved, not deleted."""
    _make_playlist(test_session, 'Safe')
    test_session.commit()
    sync_playlists_directory()

    directory = get_playlists_directory() / 'Safe'
    orphan = directory / '0001_precious.bin'
    orphan.write_bytes(b'\x00\x01 irreplaceable')

    # The playlist has no items, so this managed-looking file is "stale" -- but it has no other
    # hard link and is not one of our stubs, so it must NOT be deleted.
    sync_playlists_directory()
    assert orphan.is_file()


def test_sync_deletes_stray_root_file(test_session, test_directory):
    """A loose file dropped into the playlists root (not README, not a playlist dir) is removed.

    Only README.txt and playlist subdirectories belong at the root of this WROLPi-managed directory.
    """
    playlist = _make_playlist(test_session, 'Keeper')
    playlist.add_url(test_session, '/u/x', title='x')
    test_session.commit()
    sync_playlists_directory()

    playlists_directory = get_playlists_directory()
    stray = playlists_directory / 'foo'
    stray.write_text('junk a user dropped here')

    sync_playlists_directory()

    assert not stray.exists(), 'a stray root file should be deleted during sync'
    # The README and real playlist directories are preserved.
    assert (playlists_directory / 'README.txt').is_file()
    assert (playlists_directory / 'Keeper').is_dir()


def test_sync_refuses_dangerous_destination(test_session, test_directory):
    """The sync deletes files, so it must refuse a destination that escapes the media directory
    or overlaps another content destination (e.g. from a hand-edited wrolpi.yaml)."""
    _make_playlist(test_session, 'Any')
    test_session.commit()

    config = get_wrolpi_config()
    original = config._config['playlists_destination']
    try:
        # Traversal outside the media directory.
        config._config['playlists_destination'] = '..'
        with pytest.raises(RuntimeError):
            sync_playlists_directory()

        # The media directory itself.
        config._config['playlists_destination'] = '.'
        with pytest.raises(RuntimeError):
            sync_playlists_directory()

        # Another content destination: syncing here would delete loose files in videos/.
        config._config['playlists_destination'] = 'videos'
        with pytest.raises(RuntimeError):
            sync_playlists_directory()
    finally:
        config._config['playlists_destination'] = original

    # The default destination still works.
    sync_playlists_directory()
    assert (get_playlists_directory() / 'Any').is_dir()


def test_validate_playlists_destination(test_directory):
    """Destination validation rejects traversal and overlap with other content destinations."""
    config = get_wrolpi_config()

    assert validate_playlists_destination('playlists', config) == ''
    assert validate_playlists_destination('my/playlists', config) == ''

    assert validate_playlists_destination('', config)
    assert validate_playlists_destination('/absolute', config)
    assert validate_playlists_destination('../escape', config)
    assert validate_playlists_destination('a/../../b', config)
    # Equal to, child of, and parent of videos_destination are all rejected.
    assert validate_playlists_destination('videos', config)
    assert validate_playlists_destination('videos/playlists', config)
    assert validate_playlists_destination('zims', config)
    assert validate_playlists_destination('map/pins', config)
    assert validate_playlists_destination('tags', config)


def test_retag_moves_directory_and_prunes_empty_tag_dir(test_session, test_directory):
    """Changing a playlist's tag moves its directory and prunes the now-empty old tag directory."""
    tag = Tag(name='Survival')
    test_session.add(tag)
    test_session.flush()
    collection = _make_playlist(test_session, 'Fire Making', tag=tag)
    collection.add_url(test_session, '/u/x', title='x')
    test_session.commit()

    sync_playlists_directory()
    assert (get_playlists_directory() / 'Survival' / 'Fire Making').is_dir()

    # Remove the tag.
    collection.tag_id = None
    test_session.commit()

    sync_playlists_directory()
    assert (get_playlists_directory() / 'Fire Making').is_dir(), 'moved to top level'
    assert not (get_playlists_directory() / 'Survival').exists(), 'empty tag dir pruned'


def test_custom_directory_playlist(test_session, test_directory):
    """A playlist with a custom `directory` syncs there instead of under the playlists root."""
    custom = test_directory / 'survival' / 'fire'
    collection = _make_playlist(test_session, 'Fire Making')
    collection.directory = custom
    collection.add_url(test_session, '/u/x', title='x')
    test_session.commit()

    sync_playlists_directory()

    assert (custom / '0001_x.html').is_file()
    # No directory is created under the playlists root for this playlist.
    assert not (get_playlists_directory() / 'Fire Making').exists()


def test_custom_directory_ignores_tag(test_session, test_directory):
    """An explicit custom directory wins over tag namespacing."""
    tag = Tag(name='Survival')
    test_session.add(tag)
    test_session.flush()
    custom = test_directory / 'my' / 'spot'
    collection = _make_playlist(test_session, 'Fire Making', tag=tag)
    collection.directory = custom
    collection.add_url(test_session, '/u/x', title='x')
    test_session.commit()

    sync_playlists_directory()

    assert (custom / '0001_x.html').is_file()
    assert not (get_playlists_directory() / 'Survival').exists()


def test_cleanup_playlist_directory(test_session, test_directory):
    """cleanup_playlist_directory removes managed files (safely) and the directory if empty."""
    from wrolpi.collections.sync import cleanup_playlist_directory

    custom = test_directory / 'old' / 'spot'
    collection = _make_playlist(test_session, 'Mover')
    collection.directory = custom
    collection.add_url(test_session, '/u/x', title='x')
    test_session.commit()
    sync_playlists_directory()
    assert (custom / '0001_x.html').is_file()

    cleanup_playlist_directory(custom)
    assert not custom.exists(), 'managed stub removed and empty dir deleted'

    # A directory holding a non-managed file is kept (only managed files are removed).
    custom2 = test_directory / 'old' / 'spot2'
    custom2.mkdir(parents=True)
    (custom2 / 'keep.txt').write_text('user file')
    cleanup_playlist_directory(custom2)
    assert (custom2 / 'keep.txt').is_file()
    assert custom2.is_dir()
