import datetime
import json
import pathlib
from uuid import uuid4

import pytest

from modules.archive.lib import archive_strftime
from modules.archive.models import Archive, Domain
from wrolpi.dates import local_timezone


@pytest.fixture
def archive_directory(test_directory) -> pathlib.Path:
    path = test_directory / 'archive'
    path.mkdir()
    return path


@pytest.fixture
def archive_factory(test_session, archive_directory):
    def time_generator():
        timestamp = datetime.datetime(2000, 1, 1, 0, 0, 0)
        while True:
            timestamp += datetime.timedelta(seconds=1)
            yield timestamp

    now = time_generator()

    def _(domain: str = None, url: str = None, title: str = 'NA', contents: str = None) -> Archive:
        if domain:
            assert '/' not in domain

        title = title or str(uuid4())
        url = url or f'https://example.com/{title}'
        domain_dir = domain or title
        domain_dir = archive_directory / domain_dir
        domain_dir.mkdir(exist_ok=True)

        archive_datetime = local_timezone(next(now))
        timestamp = archive_strftime(archive_datetime)

        singlefile_path = domain_dir / f'{timestamp}_{title}.html'
        screenshot_path = domain_dir / f'{timestamp}_{title}.png'
        readability_path = domain_dir / f'{timestamp}_{title}.readability.html'
        readability_txt_path = domain_dir / f'{timestamp}_{title}.readability.txt'
        readability_json_path = domain_dir / f'{timestamp}_{title}.readability.json'

        with readability_json_path.open('wt') as fh:
            json.dump({'url': url}, fh)

        if domain:
            domain = test_session.query(Domain).filter_by(domain=domain).one_or_none()

        if not domain:
            domain = Domain(
                domain=domain_dir.name,
                directory=domain_dir,
            )
            test_session.add(domain)
            test_session.flush([domain])

        archive = Archive(
            readability_json_path=readability_json_path,
            readability_path=readability_path,
            readability_txt_path=readability_txt_path,
            screenshot_path=screenshot_path,
            singlefile_path=singlefile_path,
            title=title,
            url=url,
            domain_id=domain.id,
            contents=contents,
            archive_datetime=archive_datetime,
        )
        test_session.add(archive)

        test_session.commit()

        for path in archive.my_paths():
            path.touch()

        return archive

    return _
