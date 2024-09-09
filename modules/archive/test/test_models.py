from datetime import datetime

import pytest

from modules.archive import Domain
from wrolpi.common import get_wrolpi_config


@pytest.mark.asyncio
async def test_archive_download_destination(async_client, test_session, test_directory, archive_factory, fake_now):
    fake_now(datetime(2000, 1, 2))

    wrolpi_config = get_wrolpi_config()

    archive_factory(domain='wrolpi.org')
    domain = test_session.query(Domain).one()

    # Test the default download directory.
    assert str(domain.download_directory) == str(test_directory / 'archive/wrolpi.org')

    # Year of download is supported.
    wrolpi_config.archive_destination = 'archives/%(domain)s/%(year)s'
    assert str(domain.download_directory) == str(test_directory / 'archives/wrolpi.org/2000')

    # More download date is supported.
    wrolpi_config.archive_destination = 'archive/%(domain)s/%(year)s/%(month)s/%(day)s'
    assert str(domain.download_directory) == str(test_directory / 'archive/wrolpi.org/2000/1/2')
