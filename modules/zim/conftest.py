import asyncio
import json
import pathlib
from itertools import zip_longest
from typing import List, Dict
from uuid import uuid4

import pytest
from mock import mock

from modules.zim.downloader import KiwixCatalogDownloader, KiwixZimDownloader
from modules.zim.models import Zim
from wrolpi.common import DownloadFileInfo
from wrolpi.downloader import DownloadManager
from wrolpi.vars import PROJECT_DIR


@pytest.fixture
def kiwix_download_manager(test_download_manager) -> DownloadManager:
    kiwix_downloader = KiwixCatalogDownloader()
    kiwix_zim_downloader = KiwixZimDownloader()

    test_download_manager.register_downloader(kiwix_downloader)
    test_download_manager.register_downloader(kiwix_zim_downloader)

    yield test_download_manager


@pytest.fixture
def kiwix_download_zim(test_directory, kiwix_download_manager, test_zim_bytes, mock_downloader_download_file):
    async def do_download(download_info: DownloadFileInfo = None, expected_url: str = None,
                          download_file_side_effect=None, hrefs: List[str] = None):
        with mock.patch('modules.zim.downloader.fetch_hrefs') as mock_fetch_hrefs:
            # Fake the download, but make sure it is called correctly.  Also creates a Zim file at the output_path.
            # These are the links in the parent directory of the url.
            mock_fetch_hrefs.return_value = hrefs or ['?C=N;O=D', '?C=M;O=A', '?C=S;O=A', '?C=D;O=A', '/zim/',
                                                      'wikipedia_es_all_maxi_2023-05.zim',
                                                      'wikipedia_es_all_maxi_2023-06.zim',
                                                      'wikipedia_es_all_nopic_2023-05.zim',
                                                      'wikipedia_es_all_nopic_2023-06.zim']
            mock_downloader_download_file(test_zim_bytes)

            await kiwix_download_manager.wait_for_all_downloads()
            # Async download are hard to test, sleep to let tasks finish.
            await asyncio.sleep(0.1)
            await kiwix_download_manager.wait_for_all_downloads()

    return do_download


@pytest.fixture()
def test_zim_bytes():
    """Read the byte contents of the test Zim (test/zim.zim)."""
    path = PROJECT_DIR / 'test/zim.zim'
    return path.read_bytes()


@pytest.fixture
def zim_path_factory(test_zim_bytes, test_directory):
    """Copy the test Zim into the test directory."""

    def _(name: str = None) -> pathlib.Path:
        name = name if name else f'{uuid4()}.zim'
        path = test_directory / name
        path.write_bytes(test_zim_bytes)
        return path

    return _


@pytest.fixture
def test_zim(test_session, zim_path_factory) -> Zim:
    zim = Zim.from_paths(test_session, zim_path_factory())
    return zim


@pytest.fixture
def zim_factory(test_session, zim_path_factory, test_directory):
    def _(name: str) -> Zim:
        zim = Zim.from_paths(test_session, zim_path_factory(name))
        return zim

    return _


@pytest.fixture
def assert_zim_search(async_client, test_directory):
    from http import HTTPStatus

    async def _(search_str: str, zim_id: int, expected: Dict, tag_names: List[str] = [],
                expected_status_code: int = HTTPStatus.OK):
        content = dict(search_str=search_str, tag_names=tag_names)
        assert isinstance(zim_id, int), 'This fixture only supports Zim ids of type integer'
        request, response = await async_client.post(f'api/zim/search/{zim_id}', content=json.dumps(content))
        assert response.status_code == expected_status_code

        result = response.json['zim']

        if path := expected.get('path'):
            assert result['path'] == str(path.relative_to(test_directory))

        if estimate := expected.get('estimate'):
            assert result['estimate'] == estimate

        for response_entry, expected_entry in zip_longest(result['search'], expected['search']):
            if response_entry and not expected_entry:
                raise AssertionError(f'Response contained more entries than expected: {response_entry}')
            elif not response_entry and expected_entry:
                raise AssertionError(f'Response did not contain the expected entry: {expected_entry}')
            assert response_entry['path'] == expected_entry['path']
            assert response_entry['headline'] == expected_entry['headline']
            assert response_entry['rank'] == expected_entry['rank']

    return _
