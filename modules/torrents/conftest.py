import copy

import pytest

from modules.torrents import lib


@pytest.fixture
def test_torrents_config(test_directory):
    """An isolated torrents config in the test directory."""
    from wrolpi.api_utils import api_app
    from wrolpi.contexts import attach_shared_contexts
    if not hasattr(api_app.shared_ctx, 'switches_lock'):
        attach_shared_contexts(api_app)

    (test_directory / 'config' / 'torrents').mkdir(parents=True, exist_ok=True)
    lib.set_test_torrents_config(True)
    config = lib.get_torrents_config()
    config.initialize()
    try:
        yield config
    finally:
        lib.set_test_torrents_config(False)


class FakeQBittorrent:
    """qBittorrent's WebUI API, in memory."""

    def __init__(self, torrents=None, tags=None, preferences=None, metadata=True):
        self._torrents = {t['hash']: dict(t) for t in torrents or []}
        self._tags = list(tags or [])
        self._preferences = dict(preferences or {'upnp': True, 'lsd': True, 'listen_port': 57968,
                                                 'current_network_interface': 'vpn0'})
        self.metadata = metadata
        self.calls = []

    async def version(self):
        return 'v5.1.0'

    async def preferences(self):
        return dict(self._preferences)

    async def set_preferences(self, preferences):
        self.calls.append(('set_preferences', preferences))
        self._preferences.update(preferences)

    async def transfer_info(self):
        return {'connection_status': 'connected', 'up_info_speed': 100, 'dl_info_speed': 0}

    async def torrents(self):
        return [copy.deepcopy(t) for t in self._torrents.values()]

    async def tags(self):
        return list(self._tags)

    async def create_tags(self, *tags):
        self._tags.extend(t for t in tags if t not in self._tags)

    def _tag_set(self, hash_):
        return {t for t in self._torrents[hash_].get('tags', '').split(',') if t}

    async def add_tags(self, hashes, *tags):
        for h in hashes:
            self._torrents[h]['tags'] = ','.join(sorted(self._tag_set(h) | set(tags)))

    async def remove_tags(self, hashes, *tags):
        for h in hashes:
            self._torrents[h]['tags'] = ','.join(sorted(self._tag_set(h) - set(tags)))

    async def add(self, save_path, torrent=None, url=None, tags=None, stopped=False):
        self.calls.append(('add', save_path, torrent, url, tags, stopped))
        hash_ = (torrent or url.encode()).decode()[-40:]
        self._torrents[hash_] = dict(hash=hash_, name=f'added {hash_[:4]}', save_path=save_path,
                                     tags=','.join(tags or []), state='stoppedDL' if stopped else 'downloading',
                                     progress=0)

    async def delete(self, hashes, delete_files=False):
        self.calls.append(('delete', hashes, delete_files))
        for h in hashes:
            self._torrents.pop(h, None)

    async def export(self, hash_):
        return f'torrent {hash_}'.encode() if self.metadata else None

    async def start(self, hashes):
        self.calls.append(('start', hashes))
        for h in hashes:
            self._torrents[h]['state'] = 'downloading'

    async def stop(self, hashes):
        self.calls.append(('stop', hashes))
        for h in hashes:
            self._torrents[h]['state'] = 'stoppedDL'


@pytest.fixture
def fake_qbittorrent():
    return FakeQBittorrent
