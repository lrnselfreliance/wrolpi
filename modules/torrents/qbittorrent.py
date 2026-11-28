"""
A small client of qBittorrent's WebUI API (v2, qBittorrent 5).

qBittorrent runs inside the VPN's network namespace.  WROLPi reaches its WebUI through the namespace's uplink, from
which it needs no password (see qbittorrent_prepare.py).
"""
import json
from typing import List, Optional

import aiohttp

from wrolpi.vars import DOCKERIZED

WEBUI_PORT = 8091
# Docker: the torrent container shares the `vpn` container's network.  Raspberry Pi / Debian: the `wrolpi-vpn`
# namespace's end of its veth pair (etc/raspberrypios/wrolpi-vpn-netns.sh).
QBITTORRENT_URL = f'http://vpn:{WEBUI_PORT}' if DOCKERIZED else f'http://10.211.0.2:{WEBUI_PORT}'
TIMEOUT = aiohttp.ClientTimeout(total=10)


class QBittorrentUnavailable(Exception):
    """qBittorrent is not running, or cannot be reached."""


class QBittorrentError(Exception):
    """qBittorrent refused a request."""


class QBittorrent:

    def __init__(self, url: str = QBITTORRENT_URL):
        self.url = url.rstrip('/')

    async def _request(self, method: str, path: str, params: dict = None, data=None) -> bytes:
        try:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                async with session.request(method, f'{self.url}/api/v2/{path}', params=params, data=data) as response:
                    body = await response.read()
                    if response.status >= 400:
                        raise QBittorrentError(f'qBittorrent refused {path} ({response.status}): {body[:200]!r}')
                    return body
        except (aiohttp.ClientConnectionError, TimeoutError) as e:
            raise QBittorrentUnavailable(f'Cannot reach qBittorrent at {self.url}: {e}') from e

    async def _get_json(self, path: str, **params):
        return json.loads(await self._request('GET', path, params=params or None))

    async def version(self) -> str:
        return (await self._request('GET', 'app/version')).decode()

    async def preferences(self) -> dict:
        return await self._get_json('app/preferences')

    async def set_preferences(self, preferences: dict):
        await self._request('POST', 'app/setPreferences', data={'json': json.dumps(preferences)})

    async def transfer_info(self) -> dict:
        return await self._get_json('transfer/info')

    async def torrents(self) -> List[dict]:
        return await self._get_json('torrents/info')

    async def tags(self) -> List[str]:
        return await self._get_json('torrents/tags')

    async def create_tags(self, *tags: str):
        await self._request('POST', 'torrents/createTags', data={'tags': ','.join(tags)})

    async def add_tags(self, hashes: List[str], *tags: str):
        await self._request('POST', 'torrents/addTags', data={'hashes': '|'.join(hashes), 'tags': ','.join(tags)})

    async def remove_tags(self, hashes: List[str], *tags: str):
        await self._request('POST', 'torrents/removeTags', data={'hashes': '|'.join(hashes), 'tags': ','.join(tags)})

    async def add(self, save_path: str, torrent: bytes = None, url: str = None, tags: List[str] = None,
                  stopped: bool = False):
        """Add a torrent from a .torrent file's bytes, or a magnet link / URL."""
        form = aiohttp.FormData()
        if torrent:
            form.add_field('torrents', torrent, filename='file.torrent', content_type='application/x-bittorrent')
        elif url:
            form.add_field('urls', url)
        else:
            raise ValueError('A torrent or a URL is required')
        form.add_field('savepath', save_path)
        form.add_field('stopped', 'true' if stopped else 'false')
        if tags:
            form.add_field('tags', ','.join(tags))
        body = await self._request('POST', 'torrents/add', data=form)
        if body.strip() == b'Fails.':
            raise QBittorrentError('qBittorrent could not add the torrent')

    async def delete(self, hashes: List[str], delete_files: bool = False):
        await self._request('POST', 'torrents/delete',
                            data={'hashes': '|'.join(hashes), 'deleteFiles': 'true' if delete_files else 'false'})

    async def export(self, hash_: str) -> Optional[bytes]:
        """The .torrent file of a torrent, or None while a magnet link's metadata has not arrived."""
        try:
            return await self._request('GET', 'torrents/export', params={'hash': hash_})
        except QBittorrentError:
            return None

    async def start(self, hashes: List[str]):
        await self._request('POST', 'torrents/start', data={'hashes': '|'.join(hashes)})

    async def stop(self, hashes: List[str]):
        await self._request('POST', 'torrents/stop', data={'hashes': '|'.join(hashes)})
